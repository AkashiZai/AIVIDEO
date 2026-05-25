"""
AI Auto-Caption Video Editor — FastAPI Backend
Uses faster-whisper (CTranslate2) for 5x faster transcription.
"""
from __future__ import annotations
import asyncio, os
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models import (JobStatus, UploadResponse, TranscribeRequest, TranscribeResponse,
                     ExportRequest, ExportResponse, StatusResponse)
from job_manager import job_manager
from ffmpeg_service import get_video_duration


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="CaptionForge AI", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
@app.get("/")
async def health():
    return {"status": "ok", "service": "captionforge-api", "whisper": "faster-whisper"}


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------

@app.post("/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No file provided")

    allowed = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".flac", ".m4a", ".ogg"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported: {ext}")

    job = job_manager.create_job()
    job.original_filename = file.filename

    max_mb = int(os.environ.get("MAX_UPLOAD_MB", "500"))
    content = await file.read()
    if len(content) / (1024*1024) > max_mb:
        job_manager.delete_job(job.job_id)
        raise HTTPException(413, f"File too large. Max {max_mb}MB.")

    input_path = os.path.join(job.job_dir, f"input{ext}")
    with open(input_path, "wb") as f:
        f.write(content)
    job.input_path = input_path

    try: job.duration = get_video_duration(input_path)
    except: job.duration = 0.0

    return UploadResponse(job_id=job.job_id, filename=file.filename, duration=job.duration)


# ---------------------------------------------------------------------------
# POST /transcribe/{job_id}
# ---------------------------------------------------------------------------

@app.post("/transcribe/{job_id}", response_model=TranscribeResponse)
async def transcribe_video(job_id: str, request: TranscribeRequest = TranscribeRequest()):
    """
    Transcribe with faster-whisper.
    Accepts: model, language, initial_prompt, hotwords
    """
    job = job_manager.get_job(job_id)
    if not job: raise HTTPException(404, "Job not found")
    if not job.input_path or not os.path.exists(job.input_path):
        raise HTTPException(400, "No video file found")

    await job_manager.update_status(job_id, JobStatus.TRANSCRIBING, 0, "Starting...")

    try:
        loop = asyncio.get_event_loop()

        def sync_transcribe():
            from whisper_service import transcribe_audio

            def on_progress(pct: int, msg: str):
                asyncio.run_coroutine_threadsafe(
                    job_manager.update_progress(job_id, pct, msg), loop
                )

            return transcribe_audio(
                job.input_path,
                model_size=request.model,
                language=request.language,
                initial_prompt=request.initial_prompt,
                hotwords=request.hotwords if request.hotwords else None,
                on_progress=on_progress,
            )

        result = await loop.run_in_executor(None, sync_transcribe)
        job.transcription = result
        job.segments = result.segments
        job.duration = result.duration
        await job_manager.update_status(job_id, JobStatus.TRANSCRIBED, 100, "Done")

        return TranscribeResponse(
            job_id=job_id,
            segments=result.segments,
            language=result.language,
            duration=result.duration,
        )
    except Exception as e:
        await job_manager.update_status(job_id, JobStatus.ERROR, 0, "Failed", str(e))
        raise HTTPException(500, f"Transcription failed: {e}")


# ---------------------------------------------------------------------------
# POST /export/{job_id}
# ---------------------------------------------------------------------------

@app.post("/export/{job_id}", response_model=ExportResponse)
async def export_video(job_id: str, request: ExportRequest):
    job = job_manager.get_job(job_id)
    if not job: raise HTTPException(404, "Job not found")
    if not job.input_path or not os.path.exists(job.input_path):
        raise HTTPException(400, "No video file found")

    from ffmpeg_service import burn_captions
    output_path = os.path.join(job.job_dir, "output.mp4")
    job.output_path = output_path
    job.segments = request.segments
    job.caption_config = request.config

    await job_manager.update_status(job_id, JobStatus.EXPORTING, 0, "Starting export...")

    try:
        loop = asyncio.get_event_loop()
        def sync_export():
            def on_progress(pct, msg):
                asyncio.run_coroutine_threadsafe(job_manager.update_progress(job_id, pct, msg), loop)
            return burn_captions(job.input_path, output_path, request.segments, request.config, on_progress)

        await loop.run_in_executor(None, sync_export)
        await job_manager.update_status(job_id, JobStatus.COMPLETED, 100, "Export complete")
        return ExportResponse(job_id=job_id, message="Export complete")
    except Exception as e:
        await job_manager.update_status(job_id, JobStatus.ERROR, 0, "Failed", str(e))
        raise HTTPException(500, f"Export failed: {e}")


# ---------------------------------------------------------------------------
# GET endpoints
# ---------------------------------------------------------------------------

@app.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job: raise HTTPException(404, "Job not found")
    dl = f"/download/{job_id}" if job.status == JobStatus.COMPLETED and job.output_path else None
    return StatusResponse(job_id=job_id, status=job.status, progress=job.progress, message=job.message, download_url=dl, error=job.error)

@app.get("/download/{job_id}")
async def download_video(job_id: str):
    job = job_manager.get_job(job_id)
    if not job: raise HTTPException(404, "Job not found")
    if job.status != JobStatus.COMPLETED or not job.output_path: raise HTTPException(400, "Not ready")
    if not os.path.exists(job.output_path): raise HTTPException(404, "File not found")
    base = os.path.splitext(job.original_filename)[0]
    return FileResponse(job.output_path, media_type="video/mp4", filename=f"{base}_captioned.mp4")

@app.get("/video/{job_id}")
async def serve_video(job_id: str):
    job = job_manager.get_job(job_id)
    if not job: raise HTTPException(404, "Job not found")
    if not job.input_path or not os.path.exists(job.input_path): raise HTTPException(404, "Video not found")
    return FileResponse(job.input_path, media_type="video/mp4")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws/{job_id}")
async def ws_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    job = job_manager.get_job(job_id)
    if not job:
        await websocket.send_json({"type": "error", "message": "Job not found"})
        await websocket.close()
        return
    job_manager.register_ws(job_id, websocket)
    await websocket.send_json({"type": "status", "job_id": job_id, "status": job.status.value, "progress": job.progress, "message": job.message})
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping": await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect: pass
    finally: job_manager.unregister_ws(job_id, websocket)
