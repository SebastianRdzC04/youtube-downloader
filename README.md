# youtube-downloader

Async YouTube downloader (audio MP3 / video MP4) → upload to Nextcloud via WebDAV.

## Stack

- **Backend**: Python 3.11 + FastAPI + Uvicorn
- **Downloader**: `yt-dlp` (active fork of `youtube-dl`)
- **Audio**: `ffmpeg` (installed in the Docker image)
- **Cloud upload**: WebDAV via `httpx` (talkes to `nube.devas.sbs` with `devas` account)
- **Runtime**: Docker Compose (matches `voice-clone-minimax` pattern)

## Endpoints

| Method | Path           | Body / Query                                                                        | Response                                                                  |
| ------ | -------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `GET`  | `/health`      | —                                                                                   | `{ "status": "ok" }`                                                       |
| `POST` | `/downloads`   | `{"url": "...", "format": "mp3"\|"mp4", "quality": "best"\|"320"\|"192"\|"1080"}`  | `{ "job_id": "..." }` — starts async job, returns immediately             |
| `GET`  | `/jobs/{id}`   | —                                                                                   | `{ "status", "progress", "files": [{"name","size","url"}], "error" }`     |

### Defaults

- `format: "mp3"`, `quality: "best"` (highest bitrate available, capped at 320 kbps).
- Override per request: `mp4` for video, `quality: "1080"` for video cap, etc.

## Destination on Nextcloud

```
Devastation/sebas/descagas/musica/<playlist-or-video-title>/<n> - <title>.<ext>
```

If the URL is a single video: `Devastation/sebas/descagas/musica/<title>.<ext>`.

**IMPORTANT (case-sensitive!):** The shared folder is `Devastation/` (capital D), NOT `devastation/` (lowercase). Nextcloud on Linux is case-sensitive in WebDAV — `devas/Devastation/` is the shared folder visible to both `devas` and `SebasDevRC`, while `devas/devastation/` is a separate, private folder only the bot account can see. The `.env` must use the capital-D path. Confirmed during the 2026-09-18 first playlist download (29 cumbias initially went to `devastation/` lowercase and had to be moved with WebDAV `MOVE` to `Devastation/`).

All files are visible to `devas` (bot account) and to `SebasDevRC` (your personal account) via the share on `Devastation/`.

## Run

```bash
cd ~/develop/youtube-downloader
make dev          # foreground logs
# OR
docker compose -f docker-compose.dev.yml up -d --build
```

## CLI wrapper

`scripts/download.sh <youtube-url> [--format mp3|mp4] [--quality best|320|192|1080]`

The CLI POSTs to the API and polls `/jobs/{id}` until done, then prints the Nextcloud paths.

## Environment

Copy `.env.example` → `.env` and fill in Nextcloud credentials.

```bash
NEXTCLOUD_URL=https://nube.devas.sbs
NEXTCLOUD_USER=devas
NEXTCLOUD_PASS=<app-password>
NEXTCLOUD_BASE_DIR=Devastation/sebas/descagas/musica  # capital D — shared folder
API_PORT=50700
```

## Ports

- Dev: `50700` (block 8, slots 0-49 per `~/proyectos/PORTS.md`)
- Prod: `50750` (block 8, slots 50-99)
