"""Tests for TranscriptionConfig load/save round-trip."""

import json
import pytest

from avid_transcription.config import TranscriptionConfig


class TestConfig:
    def test_defaults(self):
        cfg = TranscriptionConfig()
        assert cfg.whisper_model == "base"
        assert cfg.language is None
        assert cfg.task == "transcribe"
        assert "srt" in cfg.output_formats
        assert "vtt" in cfg.output_formats

    def test_save_and_load(self, tmp_path, monkeypatch):
        import avid_transcription.config as config_mod
        monkeypatch.setattr(
            config_mod, "CONFIG_PATH", tmp_path / "config.json"
        )

        cfg = TranscriptionConfig()
        cfg.whisper_model = "large-v3"
        cfg.language = "fr"
        cfg.output_formats = ["srt", "avid_markers"]
        cfg.save()

        loaded = TranscriptionConfig.load()
        assert loaded.whisper_model == "large-v3"
        assert loaded.language == "fr"
        assert "srt" in loaded.output_formats
        assert "avid_markers" in loaded.output_formats

    def test_load_returns_defaults_when_no_file(self, tmp_path, monkeypatch):
        import avid_transcription.config as config_mod
        monkeypatch.setattr(
            config_mod, "CONFIG_PATH", tmp_path / "nonexistent.json"
        )
        cfg = TranscriptionConfig.load()
        assert cfg.whisper_model == "base"
