"""yt-dlp wrapper — download to a local directory and report progress.

We use yt-dlp as a library (import yt_dlp) instead of shelling out, so we can
hook the progress hook for status reporting.

References:
  https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from yt_dlp import YoutubeDL

log = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    title: str
    ext: str
    filepath: str
    filesize: int
    is_playlist_entry: bool = False
    playlist_title: str | None = None
    playlist_index: int | None = None


def _safe_name(name: str) -> str:
    """Strip filesystem-unfriendly chars but keep unicode (Nextcloud supports it)."""
    # yt-dlp's restrict-filenames is OFF, but trim trailing dots and NUL.
    return name.strip().rstrip(". ").replace("\x00", "") or "untitled"


def _format_selector(fmt: str, quality: str) -> dict:
    """Build yt-dlp `format` + postprocessors dict based on user choice.

    fmt: "mp3" | "mp4"
    quality: "best" | "320" | "192" | "1080" | "720"

    For mp3:
      - best  -> bestaudio/* (no upper cap, yt-dlp returns highest available)
      - 320   -> bestaudio[abr<=320]
      - 192   -> bestaudio[abr<=192]
    For mp4:
      - best  -> bestvideo*+bestaudio, merged into mp4
      - 1080  -> bestvideo[height<=1080]+bestaudio, mp4
      - 720   -> bestvideo[height<=720]+bestaudio, mp4
    """
    if fmt == "mp3":
        if quality == "best":
            fmt_str = "bestaudio/best"
        else:
            try:
                cap = int(quality)
                fmt_str = f"bestaudio[abr<={cap}]/bestaudio/best"
            except ValueError:
                fmt_str = "bestaudio/best"
        return {
            "format": fmt_str,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",  # 0 = keep source bitrate
                }
            ],
        }
    # mp4
    if quality == "best":
        fmt_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    else:
        try:
            cap = int(quality)
            fmt_str = (
                f"bestvideo[height<={cap}][ext=mp4]+bestaudio[ext=m4a]"
                f"/best[height<={cap}][ext=mp4]/best"
            )
        except ValueError:
            fmt_str = "best[ext=mp4]/best"
    return {
        "format": fmt_str,
        "merge_output_format": "mp4",
    }


async def download(
    url: str,
    out_dir: str,
    fmt: str = "mp3",
    quality: str = "best",
    cookies_file: str = "",
    progress_hook=None,
) -> list[DownloadResult]:
    """Download a YouTube URL (single video or playlist) to `out_dir`.

    Returns a list of DownloadResult, one per file produced. For a single
    video, the list has one entry. For a playlist, one per entry.

    progress_hook(percent_str: str, eta_str: str) is called for progress
    reporting (e.g. updating a job's progress string).
    """
    os.makedirs(out_dir, exist_ok=True)
    fmt_opts = _format_selector(fmt, quality)

    opts = {
        "outtmpl": str(Path(out_dir) / "%(playlist_index)s - %(title)s [%(id)s].%(ext)s"),
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,  # don't abort the whole playlist on one bad video
        "writethumbnail": False,
        # Default behavior: keep source files for mp3, clean intermediate for mp4
        "keepvideo": False,
        **fmt_opts,
    }
    if cookies_file and os.path.exists(cookies_file):
        opts["cookiefile"] = cookies_file

    def _hook(d: dict) -> None:
        if progress_hook is None:
            return
        if d.get("status") == "downloading":
            pct = d.get("_percent_str", "").strip()
            eta = d.get("eta_str", "").strip()
            progress_hook(pct, eta)
        elif d.get("status") == "finished":
            progress_hook("100%", "0")

    opts["progress_hooks"] = [_hook]

    def _run() -> dict:
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    info = await asyncio.to_thread(_run)
    if info is None:
        return []

    results: list[DownloadResult] = []
    # yt-dlp returns `entries` for playlists, otherwise the dict itself is the entry.
    entries = info.get("entries") if "entries" in info else [info]
    playlist_title = info.get("title") if "entries" in info else None
    for idx, entry in enumerate(entries or [], start=1):
        if entry is None:
            continue
        # After post-processing, the requested_file may differ from `filepath`.
        # yt-dlp sets `requested_downloads` with the actual final paths.
        rds = entry.get("requested_downloads") or []
        if rds:
            fp = rds[0].get("filepath")
            ext = rds[0].get("ext")
        else:
            fp = entry.get("filepath")
            ext = entry.get("ext")
        if not fp or not os.path.exists(fp):
            continue
        # Determine final ext after post-processing (mp3 conversion may rename .webm -> .mp3)
        if fmt == "mp3":
            ext = "mp3"
            # Replace the ext in fp to match the converted file
            base = re.sub(r"\.[a-z0-9]+$", "", fp)
            fp = base + ".mp3"
            if not os.path.exists(fp):
                continue
        results.append(
            DownloadResult(
                title=_safe_name(entry.get("title", "untitled")),
                ext=ext or ("mp3" if fmt == "mp3" else "mp4"),
                filepath=fp,
                filesize=os.path.getsize(fp),
                is_playlist_entry="entries" in info,
                playlist_title=playlist_title,
                playlist_index=entry.get("playlist_index", idx),
            )
        )
    return results
