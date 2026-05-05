"""
Local HTTP server that the Avid HTML panel talks to.

Runs on localhost:8765 by default. Exposes a simple REST API so the
panel can submit transcription jobs, poll progress, and retrieve results
— all without leaving Avid Media Composer.

Start with:
    avid-transcription --server
or:
    python -m avid_transcription.server
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .audio_extractor import AudioExtractor, AudioExtractorError
from .config import TranscriptionConfig
from .pipeline import TranscriptionPipeline
from .subtitle_generator import SubtitleGenerator

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8765

# When installed into the system via the .pkg the panel lives alongside the
# venv, not relative to the Python module inside site-packages.
_INSTALLED_PANEL = Path("/Library/AvidTranscription/avid_panel")
_DEV_PANEL = Path(__file__).parent.parent / "avid_panel"
PANEL_DIR = _INSTALLED_PANEL if _INSTALLED_PANEL.exists() else _DEV_PANEL

# ---------------------------------------------------------------------------
# Job store
# ---------------------------------------------------------------------------

class JobState:
    def __init__(self, job_id: str, media_path: str, config: TranscriptionConfig):
        self.job_id = job_id
        self.media_path = media_path
        self.config = config
        self.status: str = "queued"       # queued | running | done | error
        self.progress: float = 0.0
        self.message: str = "Queued"
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.created_at: float = time.time()


_jobs: Dict[str, JobState] = {}
_jobs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class TranscribeRequest(BaseModel):
    media_path: str
    whisper_model: str = "base"
    language: Optional[str] = None
    task: str = "transcribe"
    output_formats: list[str] = ["srt", "vtt", "avid_markers"]
    output_dir: Optional[str] = None
    audio_track: int = 0
    fps: float = 25.0
    vad_filter: bool = True
    word_timestamps: bool = True


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Avid Transcription Plugin",
    version="1.0.0",
    description="Local transcription server for the Avid Media Composer panel",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # panel loads from file:// or localhost
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/transcribe")
def transcribe(req: TranscribeRequest) -> dict:
    """Submit a transcription job. Returns a job_id immediately."""
    media_path = Path(req.media_path)
    if not media_path.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {req.media_path}")

    cfg = TranscriptionConfig()
    cfg.whisper_model = req.whisper_model
    cfg.language = req.language
    cfg.task = req.task
    cfg.output_formats = req.output_formats
    cfg.output_directory = req.output_dir
    cfg.vad_filter = req.vad_filter
    cfg.word_timestamps = req.word_timestamps

    job_id = str(uuid.uuid4())
    job = JobState(job_id=job_id, media_path=req.media_path, config=cfg)

    with _jobs_lock:
        _jobs[job_id] = job

    thread = threading.Thread(
        target=_run_job,
        args=(job, req.audio_track, req.fps),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/status/{job_id}")
def status(job_id: str) -> dict:
    """Poll job progress."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "result": job.result,
        "error": job.error,
    }


@app.get("/api/jobs")
def list_jobs() -> dict:
    """Return all jobs (most recent first)."""
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "media_path": j.media_path,
                "status": j.status,
                "progress": j.progress,
                "message": j.message,
            }
            for j in jobs
        ]
    }


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    with _jobs_lock:
        if job_id not in _jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        del _jobs[job_id]
    return {"deleted": job_id}


@app.get("/api/download/{job_id}/{fmt}")
def download(job_id: str, fmt: str) -> FileResponse:
    """Download a specific output file for a completed job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(status_code=404, detail="Job not found or not complete")
    files: dict = job.result.get("output_files", {})
    path = files.get(fmt)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"Format '{fmt}' not available")
    return FileResponse(path, filename=Path(path).name)


# ---------------------------------------------------------------------------
# Serve the panel HTML + static assets (CSS, JS) from the panel directory.
# StaticFiles with html=True serves index.html for "/" automatically and
# handles css/, js/ subpaths — MUST be mounted after all @app.get routes
# so the /api/* routes take priority.
# ---------------------------------------------------------------------------

def _mount_panel() -> None:
    if PANEL_DIR.exists():
        app.mount("/", StaticFiles(directory=str(PANEL_DIR), html=True), name="panel")
        logger.info("Panel mounted from %s", PANEL_DIR)
    else:
        logger.warning("Panel directory not found: %s", PANEL_DIR)


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------

def _run_job(job: JobState, audio_track: int, fps: float) -> None:
    job.status = "running"
    job.progress = 0.0
    job.message = "Starting…"

    def _progress(frac: float, msg: str) -> None:
        job.progress = frac
        job.message = msg

    try:
        pipeline = TranscriptionPipeline(job.config)
        result = pipeline.process_file(
            job.media_path,
            fps=fps,
            audio_track=audio_track,
            progress=_progress,
        )

        # Build a serialisable summary
        generator = SubtitleGenerator(job.config)
        srt_text = generator.to_srt(result.transcription.segments)
        markers_text = generator.to_avid_markers(result.transcription.segments, fps=fps)

        job.result = {
            "language": result.transcription.language,
            "duration": result.transcription.duration,
            "elapsed": result.transcription.elapsed,
            "segment_count": len(result.transcription.segments),
            "output_files": {k: str(v) for k, v in result.output_files.items()},
            "srt_preview": srt_text[:4000],
            "avid_markers": markers_text,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in result.transcription.segments
            ],
        }
        job.status = "done"
        job.progress = 1.0
        job.message = "Complete"

    except Exception as exc:
        logger.exception("Job %s failed", job.job_id)
        job.status = "error"
        job.error = str(exc)
        job.message = f"Error: {exc}"


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
    import uvicorn
    _mount_panel()
    logger.info("Starting Avid Transcription server on http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
