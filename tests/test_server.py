"""Tests for the FastAPI transcription server (no ML or FFmpeg required)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from avid_transcription.server import app, _jobs
from avid_transcription.transcriber import TranscriptSegment, TranscriptionResult


@pytest.fixture(autouse=True)
def _clear_jobs():
    """Reset job store between tests."""
    _jobs.clear()
    yield
    _jobs.clear()


@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch):
    monkeypatch.setattr(
        "avid_transcription.audio_extractor.AudioExtractor._verify_ffmpeg",
        lambda self: None,
    )


client = TestClient(app)


def _fake_result():
    segs = [TranscriptSegment(0, 0.0, 3.0, "Hello world.", language="en")]
    return TranscriptionResult(segments=segs, language="en", duration=3.0, elapsed=0.5)


class TestHealth:
    def test_health_ok(self):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


class TestTranscribe:
    def test_missing_file_returns_400(self):
        res = client.post("/api/transcribe", json={"media_path": "/nonexistent/clip.mxf"})
        assert res.status_code == 400

    def test_valid_job_is_queued(self, tmp_path):
        src = tmp_path / "clip.mxf"
        src.write_bytes(b"fake")

        with (
            patch("avid_transcription.pipeline.TranscriptionPipeline.process_file") as mock_pf,
        ):
            mock_pf.return_value = type("R", (), {
                "transcription": _fake_result(),
                "output_files": {},
                "source": src,
            })()

            res = client.post("/api/transcribe", json={"media_path": str(src)})

        assert res.status_code == 200
        data = res.json()
        assert "job_id" in data
        assert data["status"] in ("queued", "running", "done")

    def test_job_appears_in_list(self, tmp_path):
        src = tmp_path / "clip.mxf"
        src.write_bytes(b"fake")

        with patch("avid_transcription.pipeline.TranscriptionPipeline.process_file"):
            res = client.post("/api/transcribe", json={"media_path": str(src)})

        job_id = res.json()["job_id"]
        jobs_res = client.get("/api/jobs")
        ids = [j["job_id"] for j in jobs_res.json()["jobs"]]
        assert job_id in ids


class TestStatus:
    def test_unknown_job_returns_404(self):
        res = client.get("/api/status/nonexistent-id")
        assert res.status_code == 404

    def test_status_fields_present(self, tmp_path):
        src = tmp_path / "clip.mxf"
        src.write_bytes(b"fake")

        with patch("avid_transcription.pipeline.TranscriptionPipeline.process_file"):
            post = client.post("/api/transcribe", json={"media_path": str(src)})

        job_id = post.json()["job_id"]
        status = client.get(f"/api/status/{job_id}")
        assert status.status_code == 200
        data = status.json()
        for field in ("job_id", "status", "progress", "message"):
            assert field in data


class TestDeleteJob:
    def test_delete_removes_job(self, tmp_path):
        src = tmp_path / "clip.mxf"
        src.write_bytes(b"fake")

        with patch("avid_transcription.pipeline.TranscriptionPipeline.process_file"):
            post = client.post("/api/transcribe", json={"media_path": str(src)})

        job_id = post.json()["job_id"]
        del_res = client.delete(f"/api/jobs/{job_id}")
        assert del_res.status_code == 200

        status = client.get(f"/api/status/{job_id}")
        assert status.status_code == 404

    def test_delete_nonexistent_returns_404(self):
        res = client.delete("/api/jobs/nonexistent")
        assert res.status_code == 404
