"""
Pydantic models for the AI Auto-Caption Video Editor API.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    """Possible states for a captioning job."""
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    ERROR = "error"


class CaptionStyleType(str, Enum):
    """Available caption animation styles."""
    TIKTOK = "tiktok"
    SUBTITLE = "subtitle"
    WORD_BY_WORD = "word_by_word"
    KARAOKE = "karaoke"


class FontSize(str, Enum):
    """Font size presets."""
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class CaptionPosition(str, Enum):
    """Vertical position of captions on the video."""
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class WhisperModel(str, Enum):
    """Available Whisper model sizes."""
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class WordTimestamp(BaseModel):
    """A single word with start/end timing."""
    word: str
    start: float
    end: float
    confidence: float = 1.0


class TranscriptionSegment(BaseModel):
    """A transcription segment (phrase/sentence) with word-level timestamps."""
    id: int
    text: str
    start: float
    end: float
    words: list[WordTimestamp] = Field(default_factory=list)


class TranscriptionResult(BaseModel):
    """Full transcription output from Whisper."""
    segments: list[TranscriptionSegment]
    language: str = "en"
    duration: float = 0.0


class CaptionConfig(BaseModel):
    """User-selected caption style configuration."""
    style: CaptionStyleType = CaptionStyleType.TIKTOK
    font_size: FontSize = FontSize.MEDIUM
    text_color: str = "#FFFFFF"
    position: CaptionPosition = CaptionPosition.BOTTOM


# ---------------------------------------------------------------------------
# API Request / Response Models
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    """Response after uploading a video."""
    job_id: str
    filename: str
    duration: float = 0.0
    message: str = "Upload successful"


class TranscribeRequest(BaseModel):
    """Request to start transcription."""
    model: WhisperModel = WhisperModel.BASE


class TranscribeResponse(BaseModel):
    """Response with transcription result."""
    job_id: str
    segments: list[TranscriptionSegment]
    language: str
    duration: float


class ExportRequest(BaseModel):
    """Request to export video with captions."""
    segments: list[TranscriptionSegment]
    config: CaptionConfig = Field(default_factory=CaptionConfig)


class ExportResponse(BaseModel):
    """Response after starting export."""
    job_id: str
    message: str = "Export started"


class StatusResponse(BaseModel):
    """Job status response."""
    job_id: str
    status: JobStatus
    progress: int = 0
    message: str = ""
    download_url: Optional[str] = None
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
