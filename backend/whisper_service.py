"""
Whisper Service — Speech-to-text using faster-whisper (CTranslate2).

faster-whisper is ~5x faster than openai-whisper with comparable accuracy.
Uses CTranslate2 for optimized inference on CPU/GPU.
"""
from __future__ import annotations
import logging
import os
import subprocess
import tempfile
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


def _extract_audio(input_path: str) -> Optional[str]:
    """
    Extract audio from video to a temporary WAV file using ffmpeg.
    This ensures Whisper gets clean audio input regardless of the container format.
    Returns the path to the extracted WAV file, or None if extraction fails.
    """
    try:
        # Create a temp WAV file in the same directory as input
        input_dir = os.path.dirname(input_path)
        audio_path = os.path.join(input_dir, "_extracted_audio.wav")

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vn",                    # No video
            "-acodec", "pcm_s16le",   # 16-bit PCM WAV
            "-ar", "16000",           # 16kHz (optimal for Whisper)
            "-ac", "1",               # Mono
            audio_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and os.path.exists(audio_path):
            file_size = os.path.getsize(audio_path)
            logger.info(f"Extracted audio: {audio_path} ({file_size} bytes)")
            # WAV header is 44 bytes; if file is essentially empty, no audio track
            if file_size > 1000:
                return audio_path
            else:
                logger.warning("Extracted audio file is too small, likely no audio track")
                os.remove(audio_path)
                return None
        else:
            logger.warning(f"ffmpeg audio extraction failed: {result.stderr[-300:]}")
            return None
    except Exception as e:
        logger.warning(f"Audio extraction error: {e}")
        return None


def _run_transcription(
    model: FWModel,
    audio_path: str,
    language: Optional[str],
    prompt: Optional[str],
    use_vad: bool,
    temperature: float | list[float],
) -> tuple[list, object]:
    """Run a single transcription attempt with given parameters."""
    transcribe_kwargs = {
        "beam_size": 5,
        "best_of": 5,
        "temperature": temperature,
        "condition_on_previous_text": True,
        "initial_prompt": prompt if prompt else None,
        "language": language,
        "word_timestamps": True,
    }

    if use_vad:
        transcribe_kwargs["vad_filter"] = True
        transcribe_kwargs["vad_parameters"] = {
            "threshold": 0.35,               # Lower = more sensitive (default 0.5)
            "min_silence_duration_ms": 300,   # Shorter silence detection
            "min_speech_duration_ms": 100,    # Accept shorter speech chunks
            "speech_pad_ms": 200,             # Pad speech segments with 200ms
        }
    else:
        transcribe_kwargs["vad_filter"] = False

    segments_iter, info = model.transcribe(audio_path, **transcribe_kwargs)
    # Materialize the iterator
    segments_list = list(segments_iter)
    return segments_list, info


def transcribe_audio(
    audio_path: str,
    model_size: WhisperModel = WhisperModel.BASE,
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
    - Automatic fallback: if VAD returns 0 segments, retry without VAD
    - Audio pre-extraction for reliable input
    """
    if on_progress:
        on_progress(3, f"Loading model ({model_size.value})...")

    model = _get_model(model_size.value)

    # Step 1: Extract audio to ensure clean WAV input
    if on_progress:
        on_progress(8, "Extracting audio from video...")

    extracted_audio = _extract_audio(audio_path)
    actual_audio_path = extracted_audio if extracted_audio else audio_path

    if extracted_audio:
        logger.info("Using extracted WAV audio for transcription")
    else:
        logger.info("Using original file directly for transcription")

    if on_progress:
        on_progress(15, "Transcribing audio with VAD filter...")

    # Build the initial prompt with hotwords appended
    prompt = initial_prompt or ""
    if hotwords:
        # Append hotwords to the prompt so Whisper is primed to recognize them
        hw_str = ", ".join(hotwords)
        prompt = f"{prompt}. Keywords: {hw_str}" if prompt else f"Keywords: {hw_str}"

    # Attempt 1: With VAD filter and temperature=0.0
    logger.info("Attempt 1: VAD=True, temperature=0.0")
    try:
        segments_list, info = _run_transcription(
            model, actual_audio_path, language, prompt,
            use_vad=True, temperature=0.0,
        )
    except Exception as e:
        logger.warning(f"Transcription attempt 1 failed: {e}")
        segments_list = []
        info = None

    # Attempt 2: If no segments, retry WITHOUT VAD filter
    if not segments_list:
        if on_progress:
            on_progress(30, "No speech detected with VAD. Retrying without voice filter...")
        logger.info("Attempt 2: VAD=False, temperature=0.0")
        try:
            segments_list, info = _run_transcription(
                model, actual_audio_path, language, prompt,
                use_vad=False, temperature=0.0,
            )
        except Exception as e:
            logger.warning(f"Transcription attempt 2 failed: {e}")
            segments_list = []

    # Attempt 3: If still no segments, try with temperature fallback
    if not segments_list:
        if on_progress:
            on_progress(45, "Still no speech. Trying with relaxed temperature...")
        logger.info("Attempt 3: VAD=False, temperature=[0.0, 0.2, 0.4, 0.6, 0.8]")
        try:
            segments_list, info = _run_transcription(
                model, actual_audio_path, language, prompt,
                use_vad=False, temperature=[0.0, 0.2, 0.4, 0.6, 0.8],
            )
        except Exception as e:
            logger.warning(f"Transcription attempt 3 failed: {e}")
            segments_list = []

    detected_language = info.language if info else (language or "en")
    total_duration = info.duration if info else 0.0

    if on_progress:
        lang_display = detected_language.upper() if detected_language else "??"
        on_progress(20, f"Detected language: {lang_display}. Processing segments...")

    # Collect segments
    result_segments: list[TranscriptionSegment] = []
    seg_count = 0

    for seg in segments_list:
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
            pct = min(95, int(60 + (seg.end / total_duration) * 35))
            on_progress(pct, f"Segment {seg_count}: {seg.text[:40].strip()}...")

    duration = result_segments[-1].end if result_segments else total_duration

    # Cleanup extracted audio
    if extracted_audio and os.path.exists(extracted_audio):
        try:
            os.remove(extracted_audio)
        except Exception:
            pass

    if on_progress:
        if result_segments:
            on_progress(100, f"Transcription complete — {len(result_segments)} segments found")
        else:
            on_progress(100, "Transcription complete — no speech detected")

    logger.info(f"Transcription result: {len(result_segments)} segments, language={detected_language}")

    return TranscriptionResult(
        segments=result_segments,
        language=detected_language or "en",
        duration=duration,
    )
