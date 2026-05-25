# ============================================================
# Dockerfile for CaptionForge AI Backend
# faster-whisper + FFmpeg
# ============================================================

FROM python:3.11-slim

# Install FFmpeg + system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# faster-whisper installs cleanly as a wheel — no build hacks needed
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /tmp/ai-caption

ENV PORT=8000
EXPOSE 8000

CMD uvicorn main:app --host 0.0.0.0 --port $PORT
