"""
High-level pipeline that ties together extraction → transcription → subtitle generation.

Designed to be called from both the GUI and the CLI.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

from .audio_extractor import AudioExtractor
from .config import TranscriptionConfig
from .subtitle_generator import SubtitleGenerator
from .transcriber import Transcriber, TranscriptionResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, str], None]


class PipelineResult:
    def __init__(
        self,
        transcription: TranscriptionResult,
        output_files: dict[str, Path],
        source: Path,
    ):
        self.transcription = transcription
        self.output_files = output_files
        self.source = source

    def __repr__(self) -> str:
        files = ", ".join(str(p) for p in self.output_files.values())
        return (
            f"PipelineResult(source={self.source.name!r}, "
            f"language={self.transcription.language!r}, "
            f"segments={len(self.transcription.segments)}, "
            f"files=[{files}])"
        )


class TranscriptionPipeline:
    """
    Orchestrates audio extraction, transcription, and subtitle export
    for one or more media files.
    """

    def __init__(self, config: Optional[TranscriptionConfig] = None):
        self.config = config or TranscriptionConfig()
        self._extractor = AudioExtractor()
        self._transcriber = Transcriber(self.config)
        self._generator = SubtitleGenerator(self.config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_file(
        self,
        media_path: str | Path,
        output_dir: Optional[str | Path] = None,
        audio_track: int = 0,
        fps: float = 25.0,
        progress: Optional[ProgressCallback] = None,
        start_seconds: Optional[float] = None,
        duration_seconds: Optional[float] = None,
    ) -> PipelineResult:
        """
        Run the full pipeline on a single media file.

        Args:
            media_path: Video or audio file to process.
            output_dir: Where to write subtitle files. Defaults to same dir as media.
            audio_track: Zero-based audio stream index.
            fps: Frame rate used for timecode calculations.
            progress: Optional callback(float 0-1, message str).
            start_seconds: Optional in-point (for clip subsets).
            duration_seconds: Optional duration (for clip subsets).
        """
        media_path = Path(media_path)
        if output_dir is None:
            output_dir = (
                Path(self.config.output_directory)
                if self.config.output_directory
                else media_path.parent
            )

        stem = media_path.stem

        def _progress(frac: float, msg: str) -> None:
            if progress:
                progress(frac, msg)
            logger.debug("[%.0f%%] %s", frac * 100, msg)

        # Step 1: extract audio
        _progress(0.0, f"Extracting audio from {media_path.name}…")
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "audio.wav"
            self._extractor.extract(
                media_path,
                output_path=wav_path,
                audio_track=audio_track,
                start_seconds=start_seconds,
                duration_seconds=duration_seconds,
            )

            # Step 2: transcribe
            _progress(0.1, "Starting transcription…")

            def _transcribe_progress(frac: float, msg: str) -> None:
                # Transcription occupies 10–90% of overall progress bar
                _progress(0.1 + frac * 0.80, msg)

            result = self._transcriber.transcribe(wav_path, _transcribe_progress)

        # Step 3: generate subtitle files
        _progress(0.92, "Generating subtitle files…")
        output_files = self._generator.generate(
            result,
            output_dir=output_dir,
            stem=stem,
            fps=fps,
        )

        # Optional: write Avid markers into a copy of an AAF
        if self.config.export_to_aaf and self.config.avid_project_path:
            _progress(0.96, "Writing AAF markers…")
            try:
                self._write_aaf_markers(result, media_path, output_dir, fps)
            except Exception as e:
                logger.warning("AAF marker export failed: %s", e)

        _progress(1.0, "Done.")
        return PipelineResult(
            transcription=result,
            output_files=output_files,
            source=media_path,
        )

    def process_batch(
        self,
        media_paths: List[str | Path],
        output_dir: Optional[str | Path] = None,
        fps: float = 25.0,
        progress: Optional[ProgressCallback] = None,
    ) -> List[PipelineResult]:
        """Process multiple files sequentially."""
        results = []
        total = len(media_paths)
        for i, path in enumerate(media_paths):
            def _file_progress(frac: float, msg: str) -> None:
                overall = (i + frac) / total
                if progress:
                    progress(overall, f"[{i+1}/{total}] {msg}")

            result = self.process_file(
                path,
                output_dir=output_dir,
                fps=fps,
                progress=_file_progress,
            )
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_aaf_markers(
        self,
        result,
        media_path: Path,
        output_dir: Path,
        fps: float,
    ) -> None:
        from .aaf_handler import AAFHandler

        aaf_path = Path(self.config.avid_project_path)
        handler = AAFHandler(aaf_path)
        markers = AAFHandler.segments_to_markers(result.segments, fps=fps)
        handler.write_markers(
            markers,
            mob_name=media_path.stem,
            output_path=output_dir / (aaf_path.stem + "_marked.aaf"),
        )
