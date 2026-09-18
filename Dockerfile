FROM python:3.11-slim

# ffmpeg must be installed BEFORE pip install so the layer caches independently
# of requirements.txt churn. ~250MB extra, ~3-5 min cold cache.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY app/ ./app/

# yt-dlp writes here before upload to Nextcloud. Mounted as a tmpfs in compose.
RUN mkdir -p /tmp/downloads
VOLUME ["/tmp/downloads"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
