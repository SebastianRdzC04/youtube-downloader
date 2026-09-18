#!/usr/bin/env bash
# CLI wrapper: POST a job to the youtube-downloader API and poll until done.
#
# Usage:
#   ./scripts/download.sh <youtube-url> [--format mp3|mp4] [--quality best|320|192|1080|720]
#
# Defaults: format=mp3, quality=best
#
# Env:
#   API_BASE  defaults to http://localhost:50700
#
# Output: prints the job_id, then polls every 3s. On done, prints each uploaded
# file's Nextcloud path and size. Exits non-zero on failure.

set -euo pipefail

API_BASE="${API_BASE:-http://localhost:50700}"
URL="${1:-}"
FMT="mp3"
QUAL="best"

shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --format)  FMT="$2"; shift 2 ;;
    --quality) QUAL="$2"; shift 2 ;;
    -h|--help)
      grep -E '^#( |!)' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [ -z "$URL" ]; then
  echo "usage: $0 <youtube-url> [--format mp3|mp4] [--quality best|320|192|1080|720]" >&2
  exit 2
fi

# 1. Submit
RESP=$(curl -sS -X POST "$API_BASE/downloads" \
  -H 'Content-Type: application/json' \
  -d "{\"url\": \"$URL\", \"format\": \"$FMT\", \"quality\": \"$QUAL\"}")
JOB_ID=$(printf '%s' "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "✓ job_id=$JOB_ID"

# 2. Poll
while true; do
  sleep 3
  STATUS_JSON=$(curl -sS "$API_BASE/jobs/$JOB_ID")
  STATE=$(printf '%s' "$STATUS_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])")
  PROGRESS=$(printf '%s' "$STATUS_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['progress'])")
  echo "  [$STATE] $PROGRESS"
  case "$STATE" in
    done|failed) break ;;
  esac
done

# 3. Final
echo
if [ "$STATE" = "done" ]; then
  printf '%s' "$STATUS_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'✓ {len(d[\"files\"])} file(s) uploaded:')
for f in d['files']:
    size_mb = f['size'] / (1024*1024)
    print(f'  - {f[\"path\"]} ({size_mb:.1f} MB)')
    print(f'    {f[\"url\"]}')
"
  exit 0
else
  ERR=$(printf '%s' "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','unknown'))")
  echo "✗ job failed: $ERR" >&2
  exit 1
fi
