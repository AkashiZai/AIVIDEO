# ============================================================
# Dockerfile for AI Auto-Caption Video Editor Backend
# Includes Python, FFmpeg, and all dependencies
# ============================================================

FROM python:3.11-slim

# Install FFmpeg + system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .

# Pin setuptools FIRST to keep pkg_resources (needed by openai-whisper's setup.py)
# Then install all Python dependencies
RUN pip install --no-cache-dir "setuptools<81" wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create temp directory for job files
RUN mkdir -p /tmp/ai-caption

# Expose port (Railway/Render/Fly inject PORT env var)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the server — uses $PORT if set (cloud), falls back to 8000 (local)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
