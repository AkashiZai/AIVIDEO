"""
Whisper Service — Speech-to-text transcription using OpenAI Whisper.
"""

from __future__ import annotations

import whisper
import torch
import numpy as np
from typing import Optional, Callable

from models import (
    TranscriptionResult,
    TranscriptionSegment,
    WordTimestamp,
    WhisperModel,
)


# ---------------------------------------------------------------------------
# Model Cache
# ---------------------------------------------------------------------------

_loaded_models: dict[str, whisper.Whisper] = {}


def _get_model(model_name: str) -> whisper.Whisper:
    """Loads a Whisper model (cached after first load)."""
    if model_name not in _loaded_models:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _loaded_models[model_name] = whisper.load_model(model_name, device=device)
    return _loaded_models[model_name]


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def transcribe_audio(
    audio_path: str,
    model_size: WhisperModel = WhisperModel.BASE,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> TranscriptionResult:
    """
    Transcribes an audio/video file using OpenAI Whisper.

    Args:
        audio_path: Path to the media file.
        model_size: Whisper model size (base/small/medium).
        on_progress: Optional callback(progress_pct, message).

    Returns:
        TranscriptionResult with word-level timestamps.
    """
    if on_progress:
        on_progress(5, f"Loading Whisper model ({model_size.value})...")

    model = _get_model(model_size.value)

    if on_progress:
        on_progress(15, "Transcribing audio...")

    # Run Whisper with word-level timestamps
    result = model.transcribe(
        audio_path,
        word_timestamps=True,
        verbose=False,
    )

    if on_progress:
        on_progress(85, "Processing results...")

    # Extract segments with word timestamps
    segments: list[TranscriptionSegment] = []
    raw_segments = result.get("segments", [])

    for i, seg in enumerate(raw_segments):
        words: list[WordTimestamp] = []

        for w in seg.get("words", []):
            words.append(WordTimestamp(
                word=w.get("word", "").strip(),
                start=round(w.get("start", 0.0), 3),
                end=round(w.get("end", 0.0), 3),
                confidence=round(w.get("probability", 1.0), 3),
            ))

        segments.append(TranscriptionSegment(
            id=i,
            text=seg.get("text", "").strip(),
            start=round(seg.get("start", 0.0), 3),
            end=round(seg.get("end", 0.0), 3),
            words=words,
        ))

    # Detect language
    language = result.get("language", "en")

    # Calculate total duration from last segment
    duration = 0.0
    if segments:
        duration = segments[-1].end

    if on_progress:
        on_progress(100, "Transcription complete")

    return TranscriptionResult(
        segments=segments,
        language=language,
        duration=duration,
    )
