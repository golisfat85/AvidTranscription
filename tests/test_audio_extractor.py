"""Tests for AudioExtractor – mocks subprocess so FFmpeg isn't required."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from avid_transcription.audio_extractor import AudioExtractor, AudioExtractorError


class TestAudioExtractor:
    def _make_extractor(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            return AudioExtractor()

    def test_init_verifies_ffmpeg(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            extractor = AudioExtractor()
            mock_run.assert_called_once()

    def test_init_raises_if_ffmpeg_missing(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(AudioExtractorError, match="FFmpeg not found"):
                AudioExtractor()

    def test_init_raises_if_ffmpeg_nonzero(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")
            with pytest.raises(AudioExtractorError):
                AudioExtractor()

    def test_extract_raises_on_missing_source(self, tmp_path):
        extractor = self._make_extractor()
        with pytest.raises(AudioExtractorError, match="Source file not found"):
            extractor.extract(tmp_path / "nonexistent.mxf")

    def test_extract_calls_ffmpeg_with_correct_args(self, tmp_path):
        # Create a fake source file
        source = tmp_path / "clip.mxf"
        source.write_bytes(b"fake")
        out = tmp_path / "audio.wav"

        extractor = self._make_extractor()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            extractor.extract(source, output_path=out)

            args = mock_run.call_args[0][0]
            assert "ffmpeg" in args[0]
            assert str(source) in args
            assert str(out) in args
            assert "-ar" in args
            assert "16000" in args
            assert "-ac" in args
            assert "1" in args

    def test_extract_with_in_out_points(self, tmp_path):
        source = tmp_path / "clip.mxf"
        source.write_bytes(b"fake")

        extractor = self._make_extractor()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            extractor.extract(source, start_seconds=10.0, duration_seconds=30.0)

            args = mock_run.call_args[0][0]
            assert "-ss" in args
            assert "10.0" in args
            assert "-t" in args
            assert "30.0" in args

    def test_extract_raises_on_ffmpeg_error(self, tmp_path):
        source = tmp_path / "bad.mxf"
        source.write_bytes(b"fake")

        extractor = self._make_extractor()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="some ffmpeg error")
            with pytest.raises(AudioExtractorError, match="FFmpeg extraction failed"):
                extractor.extract(source)

    def test_list_audio_tracks_parses_json(self, tmp_path):
        source = tmp_path / "multi.mxf"
        source.write_bytes(b"fake")

        ffprobe_output = '{"streams": [{"codec_type": "video", "index": 0}, {"codec_type": "audio", "index": 1, "codec_name": "pcm_s24le", "channels": 2, "sample_rate": "48000", "tags": {"language": "eng"}}], "format": {"duration": "120.0"}}'

        extractor = self._make_extractor()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=ffprobe_output, stderr="")
            tracks = extractor.list_audio_tracks(source)

        assert len(tracks) == 1
        assert tracks[0]["codec"] == "pcm_s24le"
        assert tracks[0]["language"] == "eng"
        assert tracks[0]["audio_track_index"] == 0
