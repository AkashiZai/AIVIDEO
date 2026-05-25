"""
Pydantic models for the AI Auto-Caption Video Editor API.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    ERROR = "error"


class CaptionStyleType(str, Enum):
    TIKTOK = "tiktok"
    SUBTITLE = "subtitle"
    WORD_BY_WORD = "word_by_word"
    KARAOKE = "karaoke"


class FontSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class CaptionPosition(str, Enum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class WhisperModel(str, Enum):
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float
    confidence: float = 1.0


class TranscriptionSegment(BaseModel):
    id: int
    text: str
    start: float
    end: float
    words: list[WordTimestamp] = Field(default_factory=list)


class TranscriptionResult(BaseModel):
    segments: list[TranscriptionSegment]
    language: str = "en"
    duration: float = 0.0


class CaptionConfig(BaseModel):
    style: CaptionStyleType = CaptionStyleType.TIKTOK
    font_size: FontSize = FontSize.MEDIUM
    text_color: str = "#FFFFFF"
    position: CaptionPosition = CaptionPosition.BOTTOM


class UploadResponse(BaseModel):
    job_id: str
    filename: str
    duration: float = 0.0
    message: str = "Upload successful"


class TranscribeRequest(BaseModel):
    model: WhisperModel = WhisperModel.BASE


class TranscribeResponse(BaseModel):
    job_id: str
    segments: list[TranscriptionSegment]
    language: str
    duration: float


class ExportRequest(BaseModel):
    segments: list[TranscriptionSegment]
    config: CaptionConfig = Field(default_factory=CaptionConfig)


class ExportResponse(BaseModel):
    job_id: str
    message: str = "Export started"


class StatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = 0
    message: str = ""
    download_url: Optional[str] = None
    error: Optional[str] = None
