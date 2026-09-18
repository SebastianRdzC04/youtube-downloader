"""Config loaded from .env via pydantic-settings.

Critical rule (pitfall #22 from devstation-sysadmin): never write long secrets
inline in write_file payloads — they corrupt. Always populate .env from the
secure store (~/.hermes/nextcloud.env) via shell heredoc.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Nextcloud
    nextcloud_url: str = "https://nube.devas.sbs"
    nextcloud_user: str = "devas"
    nextcloud_pass: str = ""
    nextcloud_base_dir: str = "devastation/descagas/musica"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_title: str = "youtube-downloader"

    # Optional: yt-dlp cookies.txt bind-mount path inside the container
    cookies_file: str = ""

    @property
    def webdav_base(self) -> str:
        """`/remote.php/dav/files/<user>/` (no trailing slash — append paths)."""
        return f"{self.nextcloud_url.rstrip('/')}/remote.php/dav/files/{self.nextcloud_user}"


settings = Settings()
