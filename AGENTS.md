# AGENTS.md — youtube-downloader

> Read this BEFORE doing anything in this project. Other agents / future-you start here.

## Identity

- **Name**: `youtube-downloader`
- **Purpose**: Download YouTube audio/video (single or playlist) and push to Nextcloud (`Devastation/sebas/descagas/musica/` — the capital-D shared folder visible to both `devas` and `SebasDevRC`).
- **Owner**: Sebas (account `devas` on `nube.devas.sbs`).
- **Repo**: `github.com/SebastianRdzC04/youtube-downloader` (public).
- **Two-folder convention**: edit in `~/develop/youtube-downloader`, prod clone at `~/proyectos/youtube-downloader`. Never edit prod directly.

## Stack

| Layer       | Choice                                          |
| ----------- | ----------------------------------------------- |
| Language    | Python 3.11 (PEP 668 — use venv or Docker)      |
| Framework   | FastAPI + Uvicorn                               |
| Downloader  | `yt-dlp` (latest, auto-updates cookie support) |
| Audio/Video | `ffmpeg` (apt-installed in the Docker image)    |
| HTTP client | `httpx` (async, talks to Nextcloud WebDAV)      |
| Container   | Docker Compose (dev + prod profiles)            |

## Port allocation

Per `~/proyectos/PORTS.md` block 8 (next free):

- Dev: `50700`
- Prod: `50750`

Backend listens on container port `8000`, mapped to host `50700` (dev) / `50750` (prod).

## How to run

### Dev

```bash
cd ~/develop/youtube-downloader
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml logs -f backend
```

### Prod

```bash
cd ~/proyectos/youtube-downloader
docker compose -f docker-compose.prod.yml up -d --build
```

## Architecture

```
POST /downloads
    ↓
[ enqueue job in in-memory dict ]
    ↓ (background task)
[ 1. yt-dlp downloads to /tmp/<job_id>/ ]
    ↓
[ 2. ffmpeg converts (if mp3) or stays as mp4 ]
    ↓
[ 3. WebDAV PUT to Nextcloud: Devastation/sebas/descagas/musica/<playlist-or-title>/<file> ]
    ↓
[ 4. Job marked done with file list + sizes ]
```

In-memory job store is intentional — this is a personal tool, single-user, no DB needed. If multi-user is ever needed, swap dict for Redis.

## File layout

```
youtube-downloader/
├── AGENTS.md                  ← you are here
├── README.md
├── Dockerfile                 ← python:3.11-slim + ffmpeg + yt-dlp
├── docker-compose.dev.yml
├── docker-compose.prod.yml
├── .env.example
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py                ← FastAPI app, routes
│   ├── jobs.py                ← job state dict + background runner
│   ├── downloader.py          ← yt-dlp wrapper
│   ├── nextcloud.py           ← WebDAV PUT/MKCOL
│   └── config.py              ← pydantic-settings, reads .env
└── scripts/
    └── download.sh            ← CLI: POST + poll + print
```

## Conventions

- **No DB**. Jobs are stored in-process (UUID4 keys, dict, with `asyncio.Lock` for writes).
- **No authentication** on the API — it binds to localhost only (`127.0.0.1:50700`), not exposed externally. If you ever need remote access, put it behind `cloudflared`.
- **Filenames**: yt-dlp sanitizes by default. Use `--restrict-filenames` is OFF (let unicode titles through); Nextcloud WebDAV handles UTF-8 fine.
- **Cleanup**: `downloads_tmp/` volume is wiped on container restart (no persistence). Nextcloud is the source of truth post-upload.
- **Cookie support**: yt-dlp reads `cookies.txt` from `/app/cookies.txt` if present (bind-mount in dev compose). Use this if YouTube starts rate-limiting.

## Pitfalls (project-specific)

1. **`yt-dlp` needs `ffmpeg` for MP3 extraction** — install in the Dockerfile BEFORE pip install (cache layer independently).
2. **Nextcloud WebDAV MKCOL is idempotent but returns 405 if folder exists** — treat 405 as success.
3. **yt-dlp returns a list when downloading playlists, a single item for videos** — the runner must handle both.
4. **Long videos / playlists block the API** — that's why jobs are async; POST returns immediately, poll for status.
5. **YouTube rate limits unauthenticated downloads** — if 429, mount a `cookies.txt` from a logged-in browser export.
6. **Pin `yt-dlp>=2026.08.19` minimum** — versions older than mid-2026 get `The page needs to be reloaded.` from YouTube because Google changed the player client API. Confirmed during initial test (2025.01.15 broke; 2026.08.19 worked). Always `yt-dlp -U` before troubleshooting.
7. **Nextcloud WebDAV paths are CASE-SENSITIVE — `Devastation/` ≠ `devastation/` (NEW, 2026-09-18).** The shared folder between `devas` and `SebasDevRC` is `Devastation/` with a capital D. If you put `devastation/` (lowercase) in `NEXTCLOUD_BASE_DIR`, the bot creates a SEPARATE folder that only `devas` can see, and your downloads disappear from the shared view. The fix is one line in `.env`: `NEXTCLOUD_BASE_DIR=Devastation/sebas/descagas/musica`. To recover files that already went to the wrong folder, use WebDAV `MOVE` (it works cross-folder, returns 201) and `DELETE` on the empty directories.

## Verification recipe

After `up -d`:

```bash
# Health
curl -s http://localhost:50700/health
# {"status":"ok"}

# Submit a job
JOB=$(curl -s -X POST http://localhost:50700/downloads \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# Poll
curl -s http://localhost:50700/jobs/$JOB | python3 -m json.tool
```

End-to-end success = `status: "done"` + `files` array with at least one entry whose `size > 0`.
