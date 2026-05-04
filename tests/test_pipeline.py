"""
Integration-style tests for TranscriptionPipeline.
All heavy dependencies (FFmpeg, Whisper) are mocked.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from avid_transcription.config import TranscriptionConfig
from avid_transcription.pipeline import TranscriptionPipeline
from avid_transcription.transcriber import TranscriptSegment, TranscriptionResult


def _fake_result():
    segs = [
        TranscriptSegment(0, 0.0, 3.0, "Hello world.", language="en"),
        TranscriptSegment(1, 3.5, 7.0, "This is a test.", language="en"),
    ]
    return TranscriptionResult(segments=segs, language="en", duration=7.0, elapsed=1.0)


# Patch ffmpeg verification so AudioExtractor can be instantiated without FFmpeg installed.
@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch):
    monkeypatch.setattr(
        "avid_transcription.audio_extractor.AudioExtractor._verify_ffmpeg",
        lambda self: None,
    )


class TestPipeline:
    def _make_pipeline(self, formats=("srt", "vtt")):
        cfg = TranscriptionConfig()
        cfg.output_formats = list(formats)
        cfg.whisper_model = "tiny"
        pipeline = TranscriptionPipeline(cfg)
        return pipeline

    def test_process_file_generates_outputs(self, tmp_path):
        source = tmp_path / "clip.mxf"
        source.write_bytes(b"fake media")

        pipeline = self._make_pipeline(formats=["srt", "vtt"])

        with (
            patch.object(pipeline._extractor, "extract", return_value=tmp_path / "audio.wav"),
            patch.object(pipeline._transcriber, "transcribe", return_value=_fake_result()),
        ):
            result = pipeline.process_file(source, output_dir=tmp_path)

        assert "srt" in result.output_files
        assert "vtt" in result.output_files
        assert result.output_files["srt"].exists()
        assert result.output_files["vtt"].exists()

    def test_process_file_calls_extractor_with_track(self, tmp_path):
        source = tmp_path / "clip.mxf"
        source.write_bytes(b"fake")

        pipeline = self._make_pipeline()

        with (
            patch.object(pipeline._extractor, "extract", return_value=tmp_path / "audio.wav") as mock_extract,
            patch.object(pipeline._transcriber, "transcribe", return_value=_fake_result()),
        ):
            pipeline.process_file(source, audio_track=2)

        _, kwargs = mock_extract.call_args
        assert kwargs.get("audio_track") == 2

    def test_process_batch(self, tmp_path):
        files = []
        for name in ["a.mxf", "b.mxf", "c.mxf"]:
            f = tmp_path / name
            f.write_bytes(b"fake")
            files.append(f)

        pipeline = self._make_pipeline(formats=["srt"])

        with (
            patch.object(pipeline._extractor, "extract", return_value=tmp_path / "audio.wav"),
            patch.object(pipeline._transcriber, "transcribe", return_value=_fake_result()),
        ):
            results = pipeline.process_batch(files, output_dir=tmp_path)

        assert len(results) == 3

    def test_progress_callback_called(self, tmp_path):
        source = tmp_path / "clip.mxf"
        source.write_bytes(b"fake")

        pipeline = self._make_pipeline(formats=["srt"])
        calls = []

        def _cb(frac, msg):
            calls.append((frac, msg))

        with (
            patch.object(pipeline._extractor, "extract", return_value=tmp_path / "audio.wav"),
            patch.object(pipeline._transcriber, "transcribe", return_value=_fake_result()),
        ):
            pipeline.process_file(source, progress=_cb)

        assert len(calls) > 0
        # Last call should be at 100%
        assert calls[-1][0] == 1.0

    def test_result_repr(self, tmp_path):
        source = tmp_path / "clip.mxf"
        source.write_bytes(b"fake")
        pipeline = self._make_pipeline(formats=["srt"])

        with (
            patch.object(pipeline._extractor, "extract", return_value=tmp_path / "audio.wav"),
            patch.object(pipeline._transcriber, "transcribe", return_value=_fake_result()),
        ):
            result = pipeline.process_file(source, output_dir=tmp_path)

        assert "clip.mxf" in repr(result)
        assert "en" in repr(result)
