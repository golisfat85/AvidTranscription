"""
Extract audio tracks from video files using FFmpeg.
Produces a temporary WAV file suitable for Whisper ingestion.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AudioExtractorError(Exception):
    pass


class AudioExtractor:
    """Wraps FFmpeg to extract audio from any video/audio container."""

    SAMPLE_RATE = 16000   # Whisper expects 16 kHz mono
    CHANNELS = 1

    def __init__(self, ffmpeg_bin: str = "ffmpeg"):
        self.ffmpeg_bin = ffmpeg_bin
        self._verify_ffmpeg()

    def _verify_ffmpeg(self) -> None:
        try:
            result = subprocess.run(
                [self.ffmpeg_bin, "-version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                raise AudioExtractorError("FFmpeg returned non-zero exit code during version check.")
        except FileNotFoundError:
            raise AudioExtractorError(
                "FFmpeg not found. Install it from https://ffmpeg.org/download.html "
                "and ensure it is on your PATH."
            )

    def extract(
        self,
        source: str | Path,
        output_path: Optional[str | Path] = None,
        start_seconds: Optional[float] = None,
        duration_seconds: Optional[float] = None,
        audio_track: int = 0,
    ) -> Path:
        """
        Extract audio from *source* into a 16 kHz mono WAV file.

        Args:
            source: Path to the video/audio file.
            output_path: Destination WAV path. If None a temp file is created.
            start_seconds: Optional in-point offset.
            duration_seconds: Optional clip duration.
            audio_track: Zero-based audio stream index (for multi-track MXF).

        Returns:
            Path to the extracted WAV file.
        """
        source = Path(source)
        if not source.exists():
            raise AudioExtractorError(f"Source file not found: {source}")

        if output_path is None:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            output_path = Path(tmp.name)
            tmp.close()
        else:
            output_path = Path(output_path)

        cmd = [self.ffmpeg_bin, "-y"]

        if start_seconds is not None:
            cmd += ["-ss", str(start_seconds)]

        cmd += ["-i", str(source)]

        if duration_seconds is not None:
            cmd += ["-t", str(duration_seconds)]

        cmd += [
            "-map", f"0:a:{audio_track}",
            "-ac", str(self.CHANNELS),
            "-ar", str(self.SAMPLE_RATE),
            "-acodec", "pcm_s16le",
            str(output_path),
        ]

        logger.debug("FFmpeg command: %s", " ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise AudioExtractorError(
                f"FFmpeg extraction failed:\n{result.stderr}"
            )

        logger.info("Audio extracted to %s", output_path)
        return output_path

    def get_media_info(self, source: str | Path) -> dict:
        """Return basic stream information via ffprobe."""
        source = Path(source)
        ffprobe_bin = self.ffmpeg_bin.replace("ffmpeg", "ffprobe")
        cmd = [
            ffprobe_bin, "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            str(source),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise AudioExtractorError(f"ffprobe failed:\n{result.stderr}")

        import json
        return json.loads(result.stdout)

    def get_duration(self, source: str | Path) -> float:
        """Return media duration in seconds."""
        info = self.get_media_info(source)
        return float(info.get("format", {}).get("duration", 0.0))

    def list_audio_tracks(self, source: str | Path) -> list[dict]:
        """Return a list of audio stream descriptors (index, codec, channels, language)."""
        info = self.get_media_info(source)
        audio_idx = 0
        tracks = []
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "audio":
                tracks.append({
                    "stream_index": stream.get("index"),
                    "audio_track_index": audio_idx,
                    "codec": stream.get("codec_name"),
                    "channels": stream.get("channels"),
                    "sample_rate": stream.get("sample_rate"),
                    "language": stream.get("tags", {}).get("language", "und"),
                })
                audio_idx += 1
        return tracks
