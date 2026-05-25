"""
Whisper Service — Speech-to-text transcription using OpenAI Whisper.
"""
from __future__ import annotations
import whisper, torch
from typing import Optional, Callable
from models import TranscriptionResult, TranscriptionSegment, WordTimestamp, WhisperModel

_loaded_models: dict[str, whisper.Whisper] = {}

def _get_model(model_name: str) -> whisper.Whisper:
    if model_name not in _loaded_models:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _loaded_models[model_name] = whisper.load_model(model_name, device=device)
    return _loaded_models[model_name]

def transcribe_audio(audio_path: str, model_size: WhisperModel = WhisperModel.BASE, on_progress: Optional[Callable[[int, str], None]] = None) -> TranscriptionResult:
    if on_progress: on_progress(5, f"Loading Whisper model ({model_size.value})...")
    model = _get_model(model_size.value)
    if on_progress: on_progress(15, "Transcribing audio...")

    result = model.transcribe(audio_path, word_timestamps=True, verbose=False)

    if on_progress: on_progress(85, "Processing results...")

    segments: list[TranscriptionSegment] = []
    for i, seg in enumerate(result.get("segments", [])):
        words = [WordTimestamp(word=w.get("word", "").strip(), start=round(w.get("start", 0.0), 3), end=round(w.get("end", 0.0), 3), confidence=round(w.get("probability", 1.0), 3)) for w in seg.get("words", [])]
        segments.append(TranscriptionSegment(id=i, text=seg.get("text", "").strip(), start=round(seg.get("start", 0.0), 3), end=round(seg.get("end", 0.0), 3), words=words))

    language = result.get("language", "en")
    duration = segments[-1].end if segments else 0.0
    if on_progress: on_progress(100, "Transcription complete")
    return TranscriptionResult(segments=segments, language=language, duration=duration)
