# ============================================================
# Dockerfile for AI Auto-Caption Video Editor Backend
# Includes Python, FFmpeg, and all dependencies
# ============================================================

FROM python:3.11-slim

# Install FFmpeg + system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libsndfile1 git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Pin setuptools (keeps pkg_resources for openai-whisper build)
# --no-build-isolation forces whisper to use our pinned setuptools
RUN pip install --no-cache-dir "setuptools<81" wheel && \
    pip install --no-cache-dir --no-build-isolation openai-whisper==20240930 && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /tmp/ai-caption

# Railway injects $PORT env var — default to 8000 for local Docker
ENV PORT=8000
EXPOSE 8000

# NO Docker HEALTHCHECK — let Railway handle it via /health endpoint
# Docker's HEALTHCHECK can conflict with Railway's healthcheck system

# Use shell form so $PORT expands at runtime
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
