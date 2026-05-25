"""
Whisper Service — Speech-to-text using faster-whisper (CTranslate2).

faster-whisper is ~5x faster than openai-whisper with comparable accuracy.
Uses CTranslate2 for optimized inference on CPU/GPU.

Anti-hallucination measures:
- VAD filter with tuned sensitivity
- condition_on_previous_text=False to prevent repetition loops
- Compression ratio & log probability thresholds
- Post-processing to detect and remove repetitive hallucinated segments
"""
from __future__ import annotations
import logging
import os
import re
import subprocess
from collections import Counter
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


def _extract_audio_wav(input_path: str) -> Optional[str]:
    """
    Extract audio from video to a temporary WAV file using ffmpeg.
    Converts to 16kHz mono PCM — the optimal input format for Whisper.
    Returns the path to the extracted WAV file, or None if extraction fails.
    """
    try:
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
            if file_size > 1000:  # WAV header is 44 bytes; must have actual data
                return audio_path
            else:
                logger.warning("Extracted audio file too small — likely no audio track")
                os.remove(audio_path)
                return None
        else:
            logger.warning(f"ffmpeg audio extraction failed: {result.stderr[-300:]}")
            return None
    except Exception as e:
        logger.warning(f"Audio extraction error: {e}")
        return None


def _is_hallucinated_segment(text: str) -> bool:
    """
    Detect if a segment is a Whisper hallucination.

    Common hallucination patterns:
    - Extremely repetitive text (e.g. "โอเคโอเคโอเค...")
    - Common hallucination phrases repeated
    - Very short repeated units making up the whole text
    """
    text = text.strip()
    if not text:
        return True

    # Check for extremely short text that's unlikely to be real
    if len(text) <= 1:
        return True

    # ----- Repetition detection -----
    # Check if a short substring repeats to form most of the text
    clean = re.sub(r'\s+', '', text)
    text_len = len(clean)

    if text_len >= 6:
        # Try substring lengths from 1 to 10 characters
        for sub_len in range(1, min(11, text_len // 2 + 1)):
            sub = clean[:sub_len]
            repeat_count = clean.count(sub)
            coverage = (repeat_count * sub_len) / text_len
            # If a short pattern covers >70% of the text, it's likely hallucination
            if coverage > 0.70 and repeat_count >= 3:
                logger.info(f"Hallucination detected: '{sub}' repeated {repeat_count}x, coverage={coverage:.0%}")
                return True

    # ----- Known hallucination phrases -----
    hallucination_phrases = [
        "ขอบคุณที่รับชม",
        "ขอบคุณครับ",
        "ขอบคุณค่ะ",
        "สวัสดีค่ะ",
        "สวัสดีครับ",
        "thank you for watching",
        "thanks for watching",
        "please subscribe",
        "like and subscribe",
        "subtitles by",
        "translated by",
    ]
    lower_text = text.lower().strip()
    for phrase in hallucination_phrases:
        if lower_text == phrase or (len(lower_text) < len(phrase) * 2 and lower_text.count(phrase) >= 1 and len(lower_text) <= len(phrase) + 5):
            # Only flag if it's a standalone hallucination phrase that makes up the whole segment
            # Don't flag if it appears naturally within longer real text
            if text_len < len(phrase) * 3:
                logger.info(f"Known hallucination phrase detected: '{text[:50]}'")
                return True

    return False


def _filter_hallucinated_segments(segments: list) -> list:
    """
    Post-process segments to remove hallucinated ones.
    Also removes segments where the same text repeats across multiple consecutive segments.
    """
    if not segments:
        return segments

    filtered = []
    prev_text = ""

    for seg in segments:
        text = seg.text.strip() if hasattr(seg, 'text') else ""

        # Skip if this segment is individually hallucinated
        if _is_hallucinated_segment(text):
            logger.info(f"Removing hallucinated segment [{seg.start:.1f}-{seg.end:.1f}]: '{text[:60]}'")
            continue

        # Skip if identical to previous segment (consecutive duplicates)
        if text == prev_text and text:
            logger.info(f"Removing duplicate segment [{seg.start:.1f}-{seg.end:.1f}]: '{text[:60]}'")
            continue

        filtered.append(seg)
        prev_text = text

    # Final check: if ALL remaining segments have the same text, it's all hallucination
    if len(filtered) > 2:
        texts = [s.text.strip() for s in filtered if hasattr(s, 'text')]
        unique_texts = set(texts)
        if len(unique_texts) == 1:
            logger.warning("All segments have identical text — likely full hallucination, clearing results")
            return []

    removed = len(segments) - len(filtered)
    if removed > 0:
        logger.info(f"Hallucination filter: removed {removed}/{len(segments)} segments")

    return filtered


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
    - condition_on_previous_text=False to prevent repetition loops
    - Compression ratio & log prob thresholds
    - Post-processing hallucination filter
    - Audio pre-extraction for reliable input
    """
    if on_progress:
        on_progress(3, f"Loading model ({model_size.value})...")

    model = _get_model(model_size.value)

    # Step 1: Extract audio to WAV for reliable input
    if on_progress:
        on_progress(8, "Extracting audio from video...")

    extracted_audio = _extract_audio_wav(audio_path)
    actual_audio_path = extracted_audio if extracted_audio else audio_path

    if extracted_audio:
        logger.info("Using extracted WAV audio for transcription")
    else:
        logger.info("Using original file directly for transcription")

    if on_progress:
        on_progress(15, "Transcribing audio...")

    # Build the initial prompt with hotwords appended
    prompt = initial_prompt or ""
    if hotwords:
        hw_str = ", ".join(hotwords)
        prompt = f"{prompt}. Keywords: {hw_str}" if prompt else f"Keywords: {hw_str}"

    # --- Primary transcription ---
    logger.info(f"Transcribing with model={model_size.value}, language={language}, VAD=True")

    segments_iter, info = model.transcribe(
        actual_audio_path,
        # VAD filter — critical for preventing hallucination on silence
        vad_filter=True,
        vad_parameters={
            "threshold": 0.40,              # Slightly below default 0.5 for sensitivity
            "min_silence_duration_ms": 400,  # 400ms silence detection
            "min_speech_duration_ms": 150,   # Accept speech chunks ≥ 150ms
            "speech_pad_ms": 150,            # Pad detected speech by 150ms each side
        },
        # Beam search for accuracy
        beam_size=5,
        best_of=5,
        temperature=0.0,
        # IMPORTANT: False prevents "โอเคโอเค..." repetition loops
        condition_on_previous_text=False,
        # Context
        initial_prompt=prompt if prompt else None,
        # Language
        language=language,  # None = auto-detect
        # Word timestamps
        word_timestamps=True,
        # Anti-hallucination thresholds
        compression_ratio_threshold=2.4,   # Default 2.4 — reject segments with too much repetition
        log_prob_threshold=-1.0,           # Default -1.0 — reject low-confidence segments
        no_speech_threshold=0.6,           # Default 0.6 — segments with >60% no-speech prob are skipped
    )

    detected_language = info.language
    total_duration = info.duration

    if on_progress:
        lang_display = detected_language.upper() if detected_language else "??"
        on_progress(20, f"Detected language: {lang_display}. Processing segments...")

    # Materialize segments
    raw_segments = list(segments_iter)
    logger.info(f"Raw transcription produced {len(raw_segments)} segments")

    # --- Fallback: if VAD produced 0 segments, try without VAD but keep anti-hallucination ---
    if not raw_segments:
        if on_progress:
            on_progress(40, "No speech found with VAD. Retrying with relaxed settings...")

        logger.info("Fallback: VAD=False, condition_on_previous_text=False")
        segments_iter2, info2 = model.transcribe(
            actual_audio_path,
            vad_filter=False,
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=prompt if prompt else None,
            language=language,
            word_timestamps=True,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
        )
        raw_segments = list(segments_iter2)
        if info2:
            detected_language = info2.language or detected_language
            total_duration = info2.duration or total_duration
        logger.info(f"Fallback produced {len(raw_segments)} segments")

    # --- Post-processing: filter hallucinations ---
    if on_progress:
        on_progress(70, "Filtering hallucinations...")

    clean_segments = _filter_hallucinated_segments(raw_segments)
    logger.info(f"After hallucination filter: {len(clean_segments)}/{len(raw_segments)} segments kept")

    # Build result segments
    result_segments: list[TranscriptionSegment] = []
    seg_count = 0

    for seg in clean_segments:
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
            pct = min(95, int(75 + (seg.end / total_duration) * 20))
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
            on_progress(100, f"Transcription complete — {len(result_segments)} segments")
        else:
            on_progress(100, "Transcription complete — no speech detected")

    logger.info(f"Final result: {len(result_segments)} segments, language={detected_language}")

    return TranscriptionResult(
        segments=result_segments,
        language=detected_language or "en",
        duration=duration,
    )
