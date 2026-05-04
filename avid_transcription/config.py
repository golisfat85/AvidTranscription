"""Plugin-wide configuration and constants."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json
import os

CONFIG_PATH = Path.home() / ".avid_transcription" / "config.json"

WHISPER_MODELS = [
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large",
    "large-v2",
    "large-v3",
]

SUBTITLE_FORMATS = ["srt", "vtt", "avid_markers", "csv"]

SUPPORTED_VIDEO_EXTENSIONS = {
    ".mxf", ".mov", ".mp4", ".avi", ".mts", ".m2ts",
    ".mkv", ".wmv", ".flv", ".webm", ".r3d",
}

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".flac", ".aiff", ".ogg"}


@dataclass
class TranscriptionConfig:
    whisper_model: str = "base"
    language: Optional[str] = None          # None = auto-detect
    task: str = "transcribe"                # "transcribe" or "translate"
    beam_size: int = 5
    vad_filter: bool = True                 # Voice activity detection
    word_timestamps: bool = True
    use_faster_whisper: bool = True

    output_formats: list = field(default_factory=lambda: ["srt", "vtt"])
    output_directory: Optional[str] = None  # None = same dir as input

    # Subtitle styling
    max_chars_per_line: int = 42
    max_lines: int = 2
    min_duration_ms: int = 500
    max_gap_ms: int = 200                   # merge segments closer than this

    # AAF export
    export_to_aaf: bool = False
    avid_project_path: Optional[str] = None

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(self.__dict__, f, indent=2)

    @classmethod
    def load(cls) -> "TranscriptionConfig":
        if not CONFIG_PATH.exists():
            return cls()
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        obj = cls()
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj
