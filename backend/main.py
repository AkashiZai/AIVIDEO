"""
AI Auto-Caption Video Editor — FastAPI Backend

Endpoints:
  POST /upload             — Upload video, returns job_id
  POST /transcribe/{id}    — Run Whisper transcription
  POST /export/{id}        — Burn captions via FFmpeg
  GET  /status/{id}        — Job progress (0-100%)
  GET  /download/{id}      — Stream the final video file
  WS   /ws/{id}            — Real-time progress updates
"""

from __future__ import annotations

import asyncio
import os
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models import (
    JobStatus,
    UploadResponse,
    TranscribeRequest,
    TranscribeResponse,
    ExportRequest,
    ExportResponse,
    StatusResponse,
)
from job_manager import job_manager
from whisper_service import transcribe_audio
from ffmpeg_service import burn_captions, get_video_duration


# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    yield
    # Cleanup: nothing special needed


app = FastAPI(
    title="AI Auto-Caption Video Editor",
    description="Upload video → AI transcribes → burn captions → export",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------

@app.post("/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file and create a new job."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Validate file type
    allowed_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".flac"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(allowed_extensions)}",
        )

    # Create job
    job = job_manager.create_job()
    job.original_filename = file.filename

    # Check file size (limit to env MAX_UPLOAD_MB, default 500 MB)
    max_mb = int(os.environ.get("MAX_UPLOAD_MB", "500"))
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > max_mb:
        job_manager.delete_job(job.job_id)
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Maximum is {max_mb} MB.",
        )

    # Save uploaded file
    input_path = os.path.join(job.job_dir, f"input{ext}")
    try:
        with open(input_path, "wb") as f:
            f.write(content)
    except Exception as e:
        job_manager.delete_job(job.job_id)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    job.input_path = input_path

    # Get video duration
    try:
        job.duration = get_video_duration(input_path)
    except Exception:
        job.duration = 0.0

    return UploadResponse(
        job_id=job.job_id,
        filename=file.filename,
        duration=job.duration,
        message="Upload successful",
    )


# ---------------------------------------------------------------------------
# POST /transcribe/{job_id}
# ---------------------------------------------------------------------------

@app.post("/transcribe/{job_id}", response_model=TranscribeResponse)
async def transcribe_video(job_id: str, request: TranscribeRequest = TranscribeRequest()):
    """Run Whisper transcription on the uploaded video."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.input_path or not os.path.exists(job.input_path):
        raise HTTPException(status_code=400, detail="No video file found for this job")

    # Update status
    await job_manager.update_status(job_id, JobStatus.TRANSCRIBING, 0, "Starting transcription...")

    try:
        # Run Whisper in a thread pool to not block the event loop
        loop = asyncio.get_event_loop()

        async def progress_callback(pct: int, msg: str):
            await job_manager.update_progress(job_id, pct, msg)

        def sync_transcribe():
            def on_progress(pct: int, msg: str):
                asyncio.run_coroutine_threadsafe(
                    job_manager.update_progress(job_id, pct, msg),
                    loop,
                )

            return transcribe_audio(
                job.input_path,
                model_size=request.model,
                on_progress=on_progress,
            )

        result = await loop.run_in_executor(None, sync_transcribe)

        # Store transcription
        job.transcription = result
        job.segments = result.segments
        job.duration = result.duration

        await job_manager.update_status(
            job_id, JobStatus.TRANSCRIBED, 100, "Transcription complete"
        )

        return TranscribeResponse(
            job_id=job_id,
            segments=result.segments,
            language=result.language,
            duration=result.duration,
        )

    except Exception as e:
        await job_manager.update_status(
            job_id, JobStatus.ERROR, 0, "Transcription failed", str(e)
        )
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


# ---------------------------------------------------------------------------
# POST /export/{job_id}
# ---------------------------------------------------------------------------

@app.post("/export/{job_id}", response_model=ExportResponse)
async def export_video(job_id: str, request: ExportRequest):
    """Burn captions into the video using FFmpeg."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.input_path or not os.path.exists(job.input_path):
        raise HTTPException(status_code=400, detail="No video file found for this job")

    # Use provided segments (may have been edited by user)
    segments = request.segments
    config = request.config

    # Store config on job
    job.segments = segments
    job.caption_config = config

    # Output path
    output_path = os.path.join(job.job_dir, "output.mp4")
    job.output_path = output_path

    await job_manager.update_status(job_id, JobStatus.EXPORTING, 0, "Starting export...")

    try:
        loop = asyncio.get_event_loop()

        def sync_export():
            def on_progress(pct: int, msg: str):
                asyncio.run_coroutine_threadsafe(
                    job_manager.update_progress(job_id, pct, msg),
                    loop,
                )

            return burn_captions(
                job.input_path,
                output_path,
                segments,
                config,
                on_progress=on_progress,
            )

        await loop.run_in_executor(None, sync_export)

        await job_manager.update_status(
            job_id, JobStatus.COMPLETED, 100, "Export complete"
        )

        return ExportResponse(
            job_id=job_id,
            message="Export complete",
        )

    except Exception as e:
        await job_manager.update_status(
            job_id, JobStatus.ERROR, 0, "Export failed", str(e)
        )
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


# ---------------------------------------------------------------------------
# GET /status/{job_id}
# ---------------------------------------------------------------------------

@app.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    """Get the current status and progress of a job."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    download_url = None
    if job.status == JobStatus.COMPLETED and job.output_path:
        download_url = f"/download/{job_id}"

    return StatusResponse(
        job_id=job_id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        download_url=download_url,
        error=job.error,
    )


# ---------------------------------------------------------------------------
# GET /download/{job_id}
# ---------------------------------------------------------------------------

@app.get("/download/{job_id}")
async def download_video(job_id: str):
    """Stream the final captioned video file."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED or not job.output_path:
        raise HTTPException(status_code=400, detail="Video is not ready for download")

    if not os.path.exists(job.output_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    # Generate download filename
    base_name = os.path.splitext(job.original_filename)[0]
    download_name = f"{base_name}_captioned.mp4"

    return FileResponse(
        job.output_path,
        media_type="video/mp4",
        filename=download_name,
    )


# ---------------------------------------------------------------------------
# GET /video/{job_id}
# ---------------------------------------------------------------------------

@app.get("/video/{job_id}")
async def serve_video(job_id: str):
    """Serve the original uploaded video for preview in the browser."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.input_path or not os.path.exists(job.input_path):
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        job.input_path,
        media_type="video/mp4",
    )


# ---------------------------------------------------------------------------
# WebSocket /ws/{job_id}
# ---------------------------------------------------------------------------

@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time progress updates."""
    await websocket.accept()

    job = job_manager.get_job(job_id)
    if not job:
        await websocket.send_json({"type": "error", "message": "Job not found"})
        await websocket.close()
        return

    job_manager.register_ws(job_id, websocket)

    # Send current status immediately
    await websocket.send_json({
        "type": "status",
        "job_id": job_id,
        "status": job.status.value,
        "progress": job.progress,
        "message": job.message,
    })

    try:
        # Keep connection alive — wait for client messages or disconnect
        while True:
            data = await websocket.receive_text()
            # Client can send pings or commands; for now just acknowledge
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        job_manager.unregister_ws(job_id, websocket)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
