"""
Whisper Service — Speech-to-text using faster-whisper (CTranslate2).

faster-whisper is ~5x faster than openai-whisper with comparable accuracy.
Uses CTranslate2 for optimized inference on CPU/GPU.
"""
from __future__ import annotations
import logging
from typing import Optional, Callable
from faster_whisper import WhisperModel as FWModel
from models import TranscriptionResult, TranscriptionSegment, WordTimestamp, WhisperModel

logger = logging.getLogger(__name__)

# Cache loaded models by name
_loaded_models: dict[str, FWModel] = {}


def _get_model(model_name: str) -> FWModel:
    """Load and cache a faster-whisper model."""
    if model_name not in _loaded_models:
        logger.info(f"Loading faster-whisper model: {model_name}")
        # Use int8 quantization on CPU for speed; float16 on GPU
        try:
            _loaded_models[model_name] = FWModel(
                model_name,
                device="cuda",
                compute_type="float16",
            )
            logger.info(f"Loaded {model_name} on CUDA (float16)")
        except Exception:
            _loaded_models[model_name] = FWModel(
                model_name,
                device="cpu",
                compute_type="int8",
            )
            logger.info(f"Loaded {model_name} on CPU (int8)")
    return _loaded_models[model_name]


def transcribe_audio(
    audio_path: str,
    model_size: WhisperModel = WhisperModel.LARGE_V3,
    language: Optional[str] = None,
    initial_prompt: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> TranscriptionResult:
    """
    Transcribe audio using faster-whisper with:
    - VAD filter to skip silence (prevents hallucination)
    - Word-level timestamps
    - Beam search for accuracy
    - Optional language, initial_prompt, and hotwords
    """
    if on_progress:
        on_progress(5, f"Loading model ({model_size.value})...")

    model = _get_model(model_size.value)

    if on_progress:
        on_progress(15, "Transcribing audio with VAD filter...")

    # Build the initial prompt with hotwords appended
    prompt = initial_prompt or ""
    if hotwords:
        # Append hotwords to the prompt so Whisper is primed to recognize them
        hw_str = ", ".join(hotwords)
        prompt = f"{prompt}. Keywords: {hw_str}" if prompt else f"Keywords: {hw_str}"

    # Run transcription with faster-whisper
    segments_iter, info = model.transcribe(
        audio_path,
        # VAD filter — cuts silence, prevents hallucination
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 500,
        },
        # Beam search for accuracy
        beam_size=5,
        best_of=5,
        temperature=0.0,
        # Context
        condition_on_previous_text=True,
        initial_prompt=prompt if prompt else None,
        # Language
        language=language,  # None = auto-detect
        # Word timestamps
        word_timestamps=True,
    )

    detected_language = info.language
    total_duration = info.duration

    if on_progress:
        lang_display = detected_language.upper() if detected_language else "??"
        on_progress(20, f"Detected language: {lang_display}. Processing segments...")

    # Collect segments
    result_segments: list[TranscriptionSegment] = []
    seg_count = 0

    for seg in segments_iter:
        words: list[WordTimestamp] = []
        if seg.words:
            for w in seg.words:
                words.append(WordTimestamp(
                    word=w.word.strip(),
                    start=round(w.start, 3),
                    end=round(w.end, 3),
                    confidence=round(w.probability, 3),
                ))

        result_segments.append(TranscriptionSegment(
            id=seg_count,
            text=seg.text.strip(),
            start=round(seg.start, 3),
            end=round(seg.end, 3),
            words=words,
        ))
        seg_count += 1

        # Update progress proportionally
        if on_progress and total_duration > 0:
            pct = min(95, int(20 + (seg.end / total_duration) * 75))
            on_progress(pct, f"Segment {seg_count}: {seg.text[:40].strip()}...")

    duration = result_segments[-1].end if result_segments else total_duration

    if on_progress:
        on_progress(100, "Transcription complete")

    return TranscriptionResult(
        segments=result_segments,
        language=detected_language or "en",
        duration=duration,
    )
