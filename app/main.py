"""FastAPI app — endpoints: GET /health, POST /downloads, GET /jobs/{id}."""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl

from app.config import settings
from app.jobs import get_job, list_jobs, submit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("app")

app = FastAPI(title=settings.api_title, version="0.1.0")

# CORS — permissive is fine; the API binds to localhost only (no public exposure).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class DownloadRequest(BaseModel):
    url: HttpUrl = Field(..., description="YouTube URL (video or playlist)")
    format: Literal["mp3", "mp4"] = Field(
        default="mp3", description="Output format: mp3 (audio) or mp4 (video)"
    )
    quality: Literal["best", "320", "192", "1080", "720"] = Field(
        default="best", description="Quality cap (audio bitrate in kbps or video height)"
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.api_title}


@app.post("/downloads")
async def post_download(req: DownloadRequest) -> dict:
    log.info("POST /downloads url=%s format=%s quality=%s", req.url, req.format, req.quality)
    job = await submit(str(req.url), req.format, req.quality)
    return {"job_id": job.id, "status": job.status}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return job.to_dict()


@app.get("/jobs")
async def get_all_jobs() -> dict:
    """List all jobs (most recent first). Useful for the optional web UI."""
    jobs = sorted(list_jobs(), key=lambda j: j.created_at, reverse=True)
    return {"jobs": [j.to_dict() for j in jobs]}
