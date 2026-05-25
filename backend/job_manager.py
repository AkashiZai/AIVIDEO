"""
Job Manager — In-memory job state management with WebSocket broadcasting.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket

from models import (
    JobStatus,
    TranscriptionResult,
    CaptionConfig,
    TranscriptionSegment,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEMP_DIR = os.path.join(os.environ.get("TEMP", "/tmp"), "ai-caption")


# ---------------------------------------------------------------------------
# Job Data
# ---------------------------------------------------------------------------

@dataclass
class Job:
    """Represents a single captioning job."""
    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    message: str = ""
    error: Optional[str] = None

    # File paths
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    original_filename: str = ""

    # Transcription data
    transcription: Optional[TranscriptionResult] = None
    segments: list[TranscriptionSegment] = field(default_factory=list)
    caption_config: Optional[CaptionConfig] = None

    # Video metadata
    duration: float = 0.0

    @property
    def job_dir(self) -> str:
        return os.path.join(TEMP_DIR, self.job_id)


# ---------------------------------------------------------------------------
# Job Manager
# ---------------------------------------------------------------------------

class JobManager:
    """Manages job lifecycle and WebSocket connections for progress broadcasting."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._websockets: dict[str, list[WebSocket]] = {}

    # -------------------------------------------------------------------
    # Job CRUD
    # -------------------------------------------------------------------

    def create_job(self) -> Job:
        """Creates a new job with a unique ID and temp directory."""
        job_id = str(uuid.uuid4())[:8]
        job = Job(job_id=job_id)

        # Create temp directory
        os.makedirs(job.job_dir, exist_ok=True)

        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Gets a job by ID."""
        return self._jobs.get(job_id)

    def delete_job(self, job_id: str) -> None:
        """Deletes a job and cleans up its temp directory."""
        job = self._jobs.pop(job_id, None)
        if job and os.path.exists(job.job_dir):
            shutil.rmtree(job.job_dir, ignore_errors=True)

    # -------------------------------------------------------------------
    # Status updates
    # -------------------------------------------------------------------

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: int = 0,
        message: str = "",
        error: Optional[str] = None,
    ) -> None:
        """Updates job status and broadcasts via WebSocket."""
        job = self._jobs.get(job_id)
        if not job:
            return

        job.status = status
        job.progress = progress
        job.message = message
        if error:
            job.error = error

        # Broadcast to connected WebSocket clients
        await self._broadcast(job_id, {
            "type": "status",
            "job_id": job_id,
            "status": status.value,
            "progress": progress,
            "message": message,
            "error": error,
        })

    async def update_progress(
        self,
        job_id: str,
        progress: int,
        message: str = "",
    ) -> None:
        """Shorthand to update progress percentage."""
        job = self._jobs.get(job_id)
        if not job:
            return

        job.progress = progress
        job.message = message

        await self._broadcast(job_id, {
            "type": "progress",
            "job_id": job_id,
            "progress": progress,
            "message": message,
        })

    # -------------------------------------------------------------------
    # WebSocket management
    # -------------------------------------------------------------------

    def register_ws(self, job_id: str, ws: WebSocket) -> None:
        """Registers a WebSocket connection for a job."""
        if job_id not in self._websockets:
            self._websockets[job_id] = []
        self._websockets[job_id].append(ws)

    def unregister_ws(self, job_id: str, ws: WebSocket) -> None:
        """Removes a WebSocket connection."""
        if job_id in self._websockets:
            self._websockets[job_id] = [
                w for w in self._websockets[job_id] if w != ws
            ]

    async def _broadcast(self, job_id: str, data: dict) -> None:
        """Sends a message to all WebSocket clients for a job."""
        connections = self._websockets.get(job_id, [])
        dead: list[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        # Remove dead connections
        for ws in dead:
            self.unregister_ws(job_id, ws)

    # -------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------

    def cleanup_job(self, job_id: str) -> None:
        """Cleans up temp files for a completed job."""
        job = self._jobs.get(job_id)
        if job and os.path.exists(job.job_dir):
            shutil.rmtree(job.job_dir, ignore_errors=True)
        self._jobs.pop(job_id, None)


# Singleton instance
job_manager = JobManager()
