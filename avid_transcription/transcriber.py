"""
Transcription engine backed by OpenAI Whisper (via faster-whisper).

Supports both local faster-whisper and the original openai-whisper backends.
Produces a list of TranscriptSegment objects consumed by the subtitle generator.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, List, Optional

from .config import TranscriptionConfig

logger = logging.getLogger(__name__)


@dataclass
class TranscriptWord:
    word: str
    start: float   # seconds
    end: float     # seconds
    probability: float = 1.0


@dataclass
class TranscriptSegment:
    id: int
    start: float               # seconds
    end: float                 # seconds
    text: str
    words: List[TranscriptWord] = field(default_factory=list)
    language: str = ""
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


@dataclass
class TranscriptionResult:
    segments: List[TranscriptSegment]
    language: str
    duration: float            # seconds
    elapsed: float             # wall-clock seconds


ProgressCallback = Callable[[float, str], None]   # progress 0-1, message


class TranscriptionError(Exception):
    pass


class Transcriber:
    """
    High-level transcription interface.

    Prefers faster-whisper for speed; falls back to openai-whisper if not
    installed or if *config.use_faster_whisper* is False.
    """

    def __init__(self, config: Optional[TranscriptionConfig] = None):
        self.config = config or TranscriptionConfig()
        self._model = None
        self._backend: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcribe(
        self,
        audio_path: str | Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> TranscriptionResult:
        """
        Transcribe *audio_path* and return a TranscriptionResult.

        Args:
            audio_path: Path to a WAV/MP3/FLAC file (16 kHz mono recommended).
            progress_callback: Optional callable(progress: float, message: str).

        Returns:
            TranscriptionResult with segments and detected language.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        self._ensure_model_loaded(progress_callback)

        t0 = time.perf_counter()

        if self._backend == "faster-whisper":
            result = self._transcribe_faster_whisper(audio_path, progress_callback)
        else:
            result = self._transcribe_openai_whisper(audio_path, progress_callback)

        result.elapsed = time.perf_counter() - t0
        logger.info(
            "Transcription finished in %.1fs  (language=%s, segments=%d)",
            result.elapsed, result.language, len(result.segments),
        )
        return result

    def unload(self) -> None:
        """Release the model from memory."""
        self._model = None
        import gc, torch  # noqa: F401
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
        gc.collect()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_model_loaded(self, callback: Optional[ProgressCallback]) -> None:
        if self._model is not None:
            return

        model_name = self.config.whisper_model

        if self.config.use_faster_whisper:
            try:
                self._load_faster_whisper(model_name, callback)
                return
            except ImportError:
                logger.warning("faster-whisper not installed; falling back to openai-whisper")

        self._load_openai_whisper(model_name, callback)

    def _load_faster_whisper(self, model_name: str, callback: Optional[ProgressCallback]) -> None:
        from faster_whisper import WhisperModel  # type: ignore

        if callback:
            callback(0.0, f"Loading Whisper model '{model_name}'…")

        device = self._pick_device()
        compute_type = "float16" if device == "cuda" else "int8"

        self._model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )
        self._backend = "faster-whisper"
        logger.info("Loaded faster-whisper model '%s' on %s", model_name, device)

    def _load_openai_whisper(self, model_name: str, callback: Optional[ProgressCallback]) -> None:
        import whisper  # type: ignore

        if callback:
            callback(0.0, f"Loading Whisper model '{model_name}'…")

        self._model = whisper.load_model(model_name)
        self._backend = "openai-whisper"
        logger.info("Loaded openai-whisper model '%s'", model_name)

    def _transcribe_faster_whisper(
        self,
        audio_path: Path,
        callback: Optional[ProgressCallback],
    ) -> TranscriptionResult:
        from faster_whisper import decode_audio  # type: ignore

        segments_iter, info = self._model.transcribe(
            str(audio_path),
            language=self.config.language,
            task=self.config.task,
            beam_size=self.config.beam_size,
            vad_filter=self.config.vad_filter,
            word_timestamps=self.config.word_timestamps,
        )

        duration = info.duration
        segments: list[TranscriptSegment] = []

        for seg in segments_iter:
            words = []
            if self.config.word_timestamps and seg.words:
                words = [
                    TranscriptWord(
                        word=w.word,
                        start=w.start,
                        end=w.end,
                        probability=w.probability,
                    )
                    for w in seg.words
                ]

            segments.append(TranscriptSegment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                words=words,
                language=info.language,
                avg_logprob=seg.avg_logprob,
                no_speech_prob=seg.no_speech_prob,
            ))

            if callback and duration > 0:
                callback(seg.end / duration, f"Transcribed {seg.end:.1f}s / {duration:.1f}s")

        return TranscriptionResult(
            segments=segments,
            language=info.language,
            duration=duration,
            elapsed=0.0,
        )

    def _transcribe_openai_whisper(
        self,
        audio_path: Path,
        callback: Optional[ProgressCallback],
    ) -> TranscriptionResult:
        import whisper  # type: ignore

        if callback:
            callback(0.05, "Running transcription…")

        options: dict = dict(
            language=self.config.language,
            task=self.config.task,
            beam_size=self.config.beam_size,
            word_timestamps=self.config.word_timestamps,
        )

        raw = self._model.transcribe(str(audio_path), **options)

        duration = raw.get("segments", [{}])[-1].get("end", 0.0) if raw.get("segments") else 0.0
        segments: list[TranscriptSegment] = []

        for i, seg in enumerate(raw.get("segments", [])):
            words = []
            if self.config.word_timestamps:
                words = [
                    TranscriptWord(
                        word=w["word"],
                        start=w["start"],
                        end=w["end"],
                        probability=w.get("probability", 1.0),
                    )
                    for w in seg.get("words", [])
                ]

            segments.append(TranscriptSegment(
                id=i,
                start=seg["start"],
                end=seg["end"],
                text=seg["text"].strip(),
                words=words,
                language=raw.get("language", ""),
                avg_logprob=seg.get("avg_logprob", 0.0),
                no_speech_prob=seg.get("no_speech_prob", 0.0),
            ))

            if callback and duration > 0:
                callback(seg["end"] / duration, f"Transcribed {seg['end']:.1f}s / {duration:.1f}s")

        if callback:
            callback(1.0, "Transcription complete.")

        return TranscriptionResult(
            segments=segments,
            language=raw.get("language", ""),
            duration=duration,
            elapsed=0.0,
        )

    @staticmethod
    def _pick_device() -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"
