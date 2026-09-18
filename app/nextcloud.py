"""Nextcloud WebDAV client — MKCOL + PUT.

References: ~/.hermes/skills/nextcloud/SKILL.md for protocol details.
- MKCOL returns 201 (created) or 405 (already exists, treat as OK).
- PUT uploads with `Content-Type: application/octet-stream`.
- Basic auth via `httpx.BasicAuth`.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import quote

import httpx

from app.config import settings

log = logging.getLogger(__name__)


def _webdav_url(remote_path: str) -> str:
    """Build the full WebDAV URL for a remote path inside the user's namespace.

    `remote_path` is relative to `settings.webdav_base` (which already ends in
    `/remote.php/dav/files/<user>/`). Path components are URL-encoded but `/`
    is preserved.
    """
    encoded = "/".join(quote(p, safe="") for p in remote_path.split("/"))
    return f"{settings.webdav_base}/{encoded}"


def _auth() -> httpx.BasicAuth:
    return httpx.BasicAuth(settings.nextcloud_user, settings.nextcloud_pass)


async def ensure_dir(remote_dir: str) -> bool:
    """MKCOL on a path; create parents recursively.

    Returns True if the directory exists after the call (either we created it
    or it already existed; 405 Method Not Allowed is treated as OK).

    Path is relative to webdav_base (e.g. "devastation/descagas/musica/foo").
    """
    parts = [p for p in remote_dir.split("/") if p]
    accumulated: list[str] = []
    async with httpx.AsyncClient() as client:
        for part in parts:
            accumulated.append(part)
            url = _webdav_url("/".join(accumulated) + "/")
            r = await client.request("MKCOL", url, auth=_auth(), timeout=15.0)
            if r.status_code in (201, 405):
                continue
            log.error("MKCOL %s -> HTTP %s | body=%s", url, r.status_code, r.text[:200])
            return False
    return True


async def upload_file(local_path: str, remote_path: str) -> dict:
    """PUT a local file at remote_path inside the user's namespace.

    Returns {"path", "size", "url"} on success, raises httpx.HTTPStatusError
    on non-2xx.
    """
    size = os.path.getsize(local_path)
    url = _webdav_url(remote_path)
    async with httpx.AsyncClient() as client:
        with open(local_path, "rb") as f:
            data = f.read()
        r = await client.put(
            url,
            auth=_auth(),
            content=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=300.0,
        )
        if r.status_code not in (201, 204):
            raise httpx.HTTPStatusError(
                f"PUT {url} failed: HTTP {r.status_code} | body={r.text[:300]}",
                request=r.request,
                response=r,
            )
    return {
        "path": remote_path,
        "size": size,
        "url": f"{settings.nextcloud_url.rstrip('/')}/apps/files/?dir=/{remote_path.rsplit('/', 1)[0]}",
    }
