"""In-memory job store + background runner.

Each job has:
  id: UUID4
  status: pending | downloading | converting | uploading | done | failed
  progress: 0-100 (free-form string, e.g. "45.2% ETA 00:12")
  url: original YouTube URL
  format: mp3 | mp4
  quality: best | 320 | 192 | 1080 | 720
  files: list of {"name", "size", "path"}  -- populated on done
  error: optional error message
  created_at, updated_at: ISO 8601

In-memory is intentional (single-user tool, see AGENTS.md).
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

from app.config import settings
from app.downloader import download
from app.nextcloud import ensure_dir, upload_file

log = logging.getLogger(__name__)

JobStatus = Literal["pending", "downloading", "converting", "uploading", "done", "failed"]


@dataclass
class FileResult:
    name: str
    size: int
    path: str  # remote path on Nextcloud
    url: str   # web UI link to the file's folder


@dataclass
class Job:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    url: str = ""
    format: str = "mp3"
    quality: str = "best"
    status: JobStatus = "pending"
    progress: str = "0%"
    files: list[FileResult] = field(default_factory=list)
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["files"] = [asdict(f) if isinstance(f, FileResult) else f for f in self.files]
        return d


_jobs: dict[str, Job] = {}
_lock = asyncio.Lock()


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def list_jobs() -> list[Job]:
    return list(_jobs.values())


def _update(job: Job, **kwargs) -> None:
    for k, v in kwargs.items():
        setattr(job, k, v)
    job.updated_at = datetime.now(timezone.utc).isoformat()


async def submit(url: str, format: str, quality: str) -> Job:
    job = Job(url=url, format=format, quality=quality)
    async with _lock:
        _jobs[job.id] = job
    asyncio.create_task(_run(job))
    return job


async def _run(job: Job) -> None:
    """Background runner — downloads, then uploads to Nextcloud.

    The yt-dlp call is synchronous, so we run it via `asyncio.to_thread`
    (NOT `run_in_executor` + `asyncio.run` — that nests event loops and crashes
    with "asyncio.run() cannot be called from a running event loop").
    """
    workdir = tempfile.mkdtemp(prefix=f"yt-{job.id}-")
    try:
        _update(job, status="downloading", progress="0%")
        log.info("job %s: downloading %s -> %s", job.id, job.url, workdir)

        last_pct = {"v": "0%"}

        def _hook(pct: str, eta: str) -> None:
            last_pct["v"] = f"{pct} ETA {eta}" if eta else pct
            _update(job, progress=last_pct["v"])

        try:
            results = await asyncio.to_thread(
                lambda: _sync_download_blocking(job, workdir, _hook)
            )
        except Exception as e:
            log.exception("job %s: download failed", job.id)
            _update(job, status="failed", error=f"download: {e!r}")
            return

        if not results:
            _update(job, status="failed", error="no files produced (URL may be private or unavailable)")
            return

        _update(job, status="uploading", progress="uploading...")
        for r in results:
            subdir = r.playlist_title if r.is_playlist_entry else None
            subdir_safe = _safe_remote(subdir) if subdir else None
            base_parts = [settings.nextcloud_base_dir]
            if subdir_safe:
                base_parts.append(subdir_safe)
            remote_dir = "/".join(base_parts)
            try:
                await ensure_dir(remote_dir)
                if r.is_playlist_entry and r.playlist_index is not None:
                    fname = f"{r.playlist_index:02d} - {r.title}.{r.ext}"
                else:
                    fname = f"{r.title}.{r.ext}"
                remote_path = f"{remote_dir}/{fname}"
                up = await upload_file(r.filepath, remote_path)
                job.files.append(
                    FileResult(
                        name=fname,
                        size=up["size"],
                        path=up["path"],
                        url=up["url"],
                    )
                )
            except Exception as e:
                log.exception("job %s: upload %s failed", job.id, r.filepath)
                _update(job, status="failed", error=f"upload {r.filepath}: {e!r}")
                return

        _update(job, status="done", progress="100%")
        log.info("job %s: done — %d files uploaded", job.id, len(job.files))

    finally:
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass


def _safe_remote(name: str) -> str:
    """Strip Nextcloud-unfriendly chars from a single path component.

    Keep unicode (Nextcloud supports it via WebDAV URL-encoding).
    """
    name = name.replace("/", "-").strip().rstrip(". ") or "untitled"
    return name


def _sync_download_blocking(job: Job, out_dir: str, hook):
    """Synchronous wrapper that calls `asyncio.run(download(...))` once.

    This runs inside `asyncio.to_thread` (worker thread, no running loop), so
    it's safe to spin up a fresh event loop with `asyncio.run` here. Each call
    creates and tears down its own loop, which is the right shape for a single
    yt-dlp operation (we don't need a long-lived loop in the worker thread).
    """
    import asyncio as _aio
    return _aio.run(
        download(
            job.url,
            out_dir,
            fmt=job.format,
            quality=job.quality,
            cookies_file=settings.cookies_file,
            progress_hook=hook,
        )
    )
