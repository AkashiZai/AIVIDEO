"""
Whisper Service — Speech-to-text using faster-whisper (CTranslate2).

faster-whisper is ~5x faster than openai-whisper with comparable accuracy.
Uses CTranslate2 for optimized inference on CPU/GPU.

Anti-hallucination measures:
- VAD filter with tuned sensitivity
- condition_on_previous_text=False to prevent repetition loops
- Stricter compression ratio & log probability thresholds
- N-gram frequency analysis to detect repetitive hallucination patterns
- Consecutive duplicate segment removal
"""
from __future__ import annotations
import logging
import os
import re
import subprocess
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
            if file_size > 1000:
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
    Detect if a segment is a Whisper hallucination using n-gram frequency analysis.

    This catches patterns like:
    - "โอเคโอเคโอเค..." (same phrase repeated)
    - "โอโนโนโนโนโน..." (variant pattern with high-frequency substring)
    - "ขอบคุณที่รับชม" (common ending hallucination)
    """
    text = text.strip()
    if not text:
        return True
    if len(text) <= 1:
        return True

    # Remove whitespace for pattern analysis
    clean = re.sub(r'\s+', '', text)
    text_len = len(clean)

    if text_len < 6:
        return False

    # ----- N-gram frequency analysis -----
    # Instead of only checking the prefix, find the MOST FREQUENT n-gram
    # of each length and check if it dominates the text
    for ngram_len in range(1, min(12, text_len // 2 + 1)):
        # Count all n-grams of this length
        ngram_counts: dict[str, int] = {}
        for i in range(text_len - ngram_len + 1):
            ngram = clean[i:i + ngram_len]
            ngram_counts[ngram] = ngram_counts.get(ngram, 0) + 1

        if not ngram_counts:
            continue

        # Find the most frequent n-gram
        top_ngram = max(ngram_counts, key=ngram_counts.get)  # type: ignore
        top_count = ngram_counts[top_ngram]

        # Calculate how much of the text is covered by this n-gram
        coverage = (top_count * ngram_len) / text_len

        # For very short n-grams (1-2 chars), require higher coverage
        # For longer n-grams (3+), lower coverage threshold
        if ngram_len <= 2:
            threshold = 0.65
            min_repeats = 5
        elif ngram_len <= 5:
            threshold = 0.55
            min_repeats = 4
        else:
            threshold = 0.50
            min_repeats = 3

        if coverage > threshold and top_count >= min_repeats:
            logger.info(
                f"Hallucination detected: n-gram '{top_ngram}' (len={ngram_len}) "
                f"appears {top_count}x, coverage={coverage:.0%} in: '{text[:60]}'"
            )
            return True

    # ----- Known standalone hallucination phrases -----
    hallucination_phrases = [
        "ขอบคุณที่รับชม",
        "thank you for watching",
        "thanks for watching",
        "please subscribe",
        "like and subscribe",
        "subtitles by",
        "translated by",
    ]
    lower_text = text.lower().strip()
    for phrase in hallucination_phrases:
        # Only flag if the phrase IS the whole segment (or nearly)
        if lower_text == phrase or (len(lower_text) < len(phrase) + 10 and phrase in lower_text):
            logger.info(f"Known hallucination phrase: '{text[:60]}'")
            return True

    return False


def _filter_hallucinations(segments: list) -> list:
    """
    Post-process segments to remove hallucinated ones.
    - Removes individually hallucinated segments (repetitive text)
    - Removes consecutive duplicate segments
    - Removes all segments if they're all identical (full hallucination)
    """
    if not segments:
        return segments

    filtered = []
    prev_text = ""

    for seg in segments:
        text = seg.text.strip() if hasattr(seg, 'text') else ""

        # Skip individually hallucinated segments
        if _is_hallucinated_segment(text):
            logger.info(f"Removing hallucinated segment [{seg.start:.1f}-{seg.end:.1f}]: '{text[:80]}'")
            continue

        # Skip consecutive duplicates
        if text == prev_text and text:
            logger.info(f"Removing duplicate segment [{seg.start:.1f}-{seg.end:.1f}]: '{text[:60]}'")
            continue

        filtered.append(seg)
        prev_text = text

    # If ALL remaining segments have identical text → full hallucination
    if len(filtered) > 2:
        texts = [s.text.strip() for s in filtered if hasattr(s, 'text')]
        unique_texts = set(texts)
        if len(unique_texts) == 1:
            logger.warning("All segments have identical text — full hallucination, clearing results")
            return []

    removed = len(segments) - len(filtered)
    if removed > 0:
        logger.info(f"Hallucination filter: removed {removed}/{len(segments)} segments, kept {len(filtered)}")

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
    Transcribe audio using faster-whisper with robust anti-hallucination.

    Features:
    - VAD filter to skip silence
    - Word-level timestamps
    - Beam search for accuracy
    - condition_on_previous_text=False to prevent repetition loops
    - Strict compression ratio threshold to reject repetitive output
    - N-gram frequency hallucination post-filter
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

    # --- Primary transcription with VAD ---
    logger.info(f"Transcribing: model={model_size.value}, language={language}, VAD=True")

    segments_iter, info = model.transcribe(
        actual_audio_path,
        # VAD filter — critical for preventing hallucination on silence
        vad_filter=True,
        vad_parameters={
            "threshold": 0.40,              # Slightly below default 0.5
            "min_silence_duration_ms": 400,
            "min_speech_duration_ms": 150,
            "speech_pad_ms": 150,
        },
        # Beam search
        beam_size=5,
        best_of=5,
        temperature=0.0,
        # CRITICAL: False prevents repetition loops ("โอเคโอเค...", "โนโนโน...")
        condition_on_previous_text=False,
        # Context
        initial_prompt=prompt if prompt else None,
        # Language
        language=language,  # None = auto-detect
        # Word timestamps
        word_timestamps=True,
        # Anti-hallucination thresholds (stricter than defaults)
        compression_ratio_threshold=1.8,    # Default 2.4 — stricter to catch repetition
        log_prob_threshold=-0.5,            # Default -1.0 — stricter confidence filter
        no_speech_threshold=0.5,            # Default 0.6 — more aggressive no-speech detection
    )

    detected_language = info.language
    total_duration = info.duration

    if on_progress:
        lang_display = detected_language.upper() if detected_language else "??"
        on_progress(20, f"Detected language: {lang_display}. Processing segments...")

    # Materialize segments
    raw_segments = list(segments_iter)
    logger.info(f"Raw transcription: {len(raw_segments)} segments")

    # --- Fallback if VAD produced 0 segments ---
    if not raw_segments:
        if on_progress:
            on_progress(40, "No speech with VAD. Retrying with relaxed settings...")

        logger.info("Fallback: VAD=False, relaxed thresholds")
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
            compression_ratio_threshold=2.0,
            log_prob_threshold=-0.8,
            no_speech_threshold=0.6,
        )
        raw_segments = list(segments_iter2)
        if info2:
            detected_language = info2.language or detected_language
            total_duration = info2.duration or total_duration
        logger.info(f"Fallback: {len(raw_segments)} segments")

    # --- Post-processing: filter hallucinations ---
    if on_progress:
        on_progress(70, "Filtering hallucinations...")

    clean_segments = _filter_hallucinations(raw_segments)
    logger.info(f"After hallucination filter: {len(clean_segments)}/{len(raw_segments)} segments kept")

    # Build result
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
            on_progress(100, f"Done — {len(result_segments)} segments")
        else:
            on_progress(100, "Done — no speech detected")

    logger.info(f"Final: {len(result_segments)} segments, lang={detected_language}")

    return TranscriptionResult(
        segments=result_segments,
        language=detected_language or "en",
        duration=duration,
    )
