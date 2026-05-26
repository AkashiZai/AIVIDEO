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

Thai song/music optimizations:
- Auto-injected Thai initial prompt covering vowels AND consonant pairs Whisper confuses
- Relaxed log_prob_threshold for Thai (Thai audio has naturally lower confidence)
- Music-aware VAD parameters (lower threshold, shorter silence detection)
- Temperature fallback sampling for ambiguous characters
- Higher beam_size (10) and best_of (10) for more thorough search
- condition_on_previous_text=True for Thai (context helps disambiguate consonants)
- Thai word correction post-processing for common Whisper mistakes
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
        model = None
        # Try CUDA first
        try:
            model = FWModel(
                model_name,
                device="cuda",
                compute_type="float16",
            )
            # Quick probe to verify CUDA actually works at runtime
            # (cublas DLL might be missing even if CUDA loads)
            import numpy as np
            import io, wave, tempfile
            # Create a tiny 0.5s silent WAV to test
            sr = 16000
            samples = np.zeros(sr // 2, dtype=np.int16)
            tmp = os.path.join(tempfile.gettempdir(), "_whisper_cuda_test.wav")
            with wave.open(tmp, "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(samples.tobytes())
            # This will trigger cublas load
            list(model.transcribe(tmp, language="en", beam_size=1, vad_filter=False)[0])
            os.remove(tmp)
            logger.info(f"Loaded {model_name} on CUDA (float16) — verified working")
        except Exception as e:
            logger.warning(f"CUDA failed ({e}), falling back to CPU")
            model = FWModel(
                model_name,
                device="cpu",
                compute_type="int8",
            )
            logger.info(f"Loaded {model_name} on CPU (int8)")
        _loaded_models[model_name] = model
    return _loaded_models[model_name]


def _extract_audio_wav(input_path: str) -> Optional[str]:
    """
    Extract audio from video to a temporary WAV file using ffmpeg.
    Tries multiple codec strategies for compatibility with different ffmpeg builds.
    Returns the path to the extracted WAV file, or None if extraction fails.
    """
    input_dir = os.path.dirname(input_path)
    audio_path = os.path.join(input_dir, "_extracted_audio.wav")

    # Multiple strategies — some ffmpeg builds don't have all codecs
    strategies = [
        # Strategy 1: Standard PCM WAV (best for Whisper)
        [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            audio_path,
        ],
        # Strategy 2: Let ffmpeg auto-select codec for WAV container
        [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-ar", "16000", "-ac", "1",
            audio_path,
        ],
        # Strategy 3: Use FLAC (lossless, widely supported)
        [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-acodec", "flac", "-ar", "16000", "-ac", "1",
            audio_path.replace(".wav", ".flac"),
        ],
    ]

    for i, cmd in enumerate(strategies):
        try:
            target = cmd[-1]  # output path
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and os.path.exists(target):
                file_size = os.path.getsize(target)
                if file_size > 1000:
                    logger.info(
                        f"Audio extracted (strategy {i+1}): {target} "
                        f"({file_size} bytes)"
                    )
                    return target
                else:
                    logger.warning(f"Strategy {i+1}: file too small ({file_size}b)")
                    os.remove(target)
            else:
                stderr_tail = result.stderr[-200:] if result.stderr else "no stderr"
                logger.info(f"Strategy {i+1} failed: {stderr_tail}")
        except Exception as e:
            logger.info(f"Strategy {i+1} error: {e}")

    logger.warning("All ffmpeg strategies failed — Whisper will use video directly")
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


# Thai-specific initial prompt — contains common Thai vowels, consonant pairs,
# and word patterns to guide Whisper's decoder toward correct Thai character mappings.
# Covers BOTH vowel and consonant confusion that Whisper commonly makes.
_THAI_INITIAL_PROMPT = (
    "เพลงไทย เนื้อเพลงภาษาไทย ร้องเพลง "
    # Vowels — all Thai vowel forms
    "สระอา สระอี สระอู สระเอ สระโอ สระแอ สระออ สระอือ สระอัว "
    "ไม่ ใจ ได้ ไป ใน ให้ ใช้ ไว้ ไหม ไม้ "
    "เธอ เขา แล้ว แต่ เพราะ เท่า แค่ เคย "
    # Consonant pairs Whisper commonly confuses
    "กว่า กับ กลับ กลัว ก็ กัน การ ก่อน "
    "ชอบ ช่วง ชีวิต ชื่อ ช้า "
    "ซ่อน ซึ้ง ซื้อ "
    "สาย สุด สวย สอง สะออน สบาย "
    "ทำ ทำไม ที่ ทาง ท้อง ทุก เท่าไหร่ "
    "ตัว ต้อง ตาม ตา ตลอด "
    "คน ความ คิด คิดถึง คง คอย คืน "
    "พอ เพียง เพราะ พูด พบ "
    "ฟัง ฟ้า "
    # Common song words with correct spelling
    "รัก หัวใจ ร้องไห้ ห่วง หา หมด "
    "อยาก อยู่ อีก อ้อม "
    "ยัง เย็น ยอม ยาก "
    "จะ จำ เจ็บ จริง "
    "ผ่าน ผิด "
    "นอน นะ น้ำตา "
    "มี ไม่เคย เมื่อ "
    "วัน ว่า กว่า อีกกว่า "
    "บอก บ้าง "
    "ลืม เลย เล่น แล้ว "
    "ดี ได้ ด้วย "
)


# Common Thai word corrections for Whisper mistakes.
# Maps incorrect transcription → correct word.
# Only applied when language is Thai.
_THAI_CORRECTIONS: dict[str, str] = {
    # Consonant confusion: ซ→ช, ซ→ส
    "ซอบ": "ชอบ",
    "ซ่อบ": "ชอบ",
    "ซับ": "ชอบ",
    "ซีวิต": "ชีวิต",
    "ซ่วง": "ช่วง",
    "ซื่อ": "ชื่อ",
    "ซ้าย": "สาย",
    "ซวย": "สวย",
    "ซุด": "สุด",
    "ซอง": "สอง",
    "ซบาย": "สบาย",
    # Consonant confusion: dropped ก in กว่า
    "จว่า": "กว่า",
    # Consonant confusion: ท→ต, ต→ท
    "ท่อง": "ต้อง",
    "เทา": "เท่า",
    "เท่าไร่": "เท่าไหร่",
    "เทาไหร่": "เท่าไหร่",
    "เท่าหร่": "เท่าไหร่",
    # Consonant confusion: ค→ก
    "คลับ": "กลับ",
    "คลัว": "กลัว",
    # Tone mark errors
    "ม่าก": "มาก",
    "ร้อง": "ร้อง",
    # Common word-boundary errors
    "สะ ออน": "สะออน",
    "หัว ใจ": "หัวใจ",
    "คิด ถึง": "คิดถึง",
    "ร้อง ไห้": "ร้องไห้",
    "ทำ ไม": "ทำไม",
    "เท่า ไหร่": "เท่าไหร่",
}


def _apply_thai_corrections(text: str) -> str:
    """Apply Thai word corrections to fix common Whisper transcription mistakes."""
    result = text
    for wrong, correct in _THAI_CORRECTIONS.items():
        result = result.replace(wrong, correct)
    return result


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
    - Thai song optimization: vowel-rich prompt, relaxed thresholds, temp fallback
    - Gemini AI post-correction for Thai spelling errors (if API key configured)
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

    # Detect if this is Thai content
    is_thai = language and language.lower() == "th"

    # Build the initial prompt with Thai boost and hotwords
    prompt = initial_prompt or ""
    if is_thai:
        # Prepend Thai vowel-rich prompt to guide decoder
        prompt = _THAI_INITIAL_PROMPT + (" " + prompt if prompt else "")
        logger.info("Thai language detected — using Thai vowel-rich initial prompt")
    if hotwords:
        hw_str = ", ".join(hotwords)
        prompt = f"{prompt}. Keywords: {hw_str}" if prompt else f"Keywords: {hw_str}"

    # --- Determine parameters based on language ---
    # Thai songs/music need relaxed thresholds because:
    # 1. Background music lowers speech confidence scores
    # 2. Singing stretches vowels, making them harder to classify
    # 3. Thai tones + music pitch = lower log probabilities
    if is_thai:
        vad_threshold = 0.35          # Lower for music (captures singing over instruments)
        min_silence_ms = 300          # Shorter silence detection for song lyrics
        min_speech_ms = 100           # Capture shorter sung phrases
        speech_pad_ms = 200           # More padding to catch vowel tails
        compression_thresh = 2.2      # Relaxed — Thai song repeats are natural
        log_prob_thresh = -0.8        # Relaxed — Thai confidence is naturally lower
        no_speech_thresh = 0.5        # Keep aggressive no-speech detection
        temperature = (0.0, 0.2, 0.4) # Temperature fallback for ambiguous characters
        beam = 10                     # More hypotheses → better consonant choices
        best = 10                     # More candidates to pick from
        use_prev_text = True          # Context from prev lyrics helps Thai consonants
        logger.info("Using Thai-optimized transcription parameters (beam=10, condition_prev=True)")
    else:
        vad_threshold = 0.40
        min_silence_ms = 400
        min_speech_ms = 150
        speech_pad_ms = 150
        compression_thresh = 1.8
        log_prob_thresh = -0.5
        no_speech_thresh = 0.5
        temperature = 0.0
        beam = 5
        best = 5
        use_prev_text = False         # Off for non-Thai to prevent hallucination

    # --- Primary transcription with VAD ---
    logger.info(f"Transcribing: model={model_size.value}, language={language}, VAD=True, thai_mode={is_thai}")

    segments_iter, info = model.transcribe(
        actual_audio_path,
        # VAD filter — critical for preventing hallucination on silence
        vad_filter=True,
        vad_parameters={
            "threshold": vad_threshold,
            "min_silence_duration_ms": min_silence_ms,
            "min_speech_duration_ms": min_speech_ms,
            "speech_pad_ms": speech_pad_ms,
        },
        # Beam search — larger for Thai to explore more consonant hypotheses
        beam_size=beam,
        best_of=best,
        temperature=temperature,
        # For Thai: True helps carry context (consonant disambiguation)
        # For others: False prevents repetition loops ("โอเคโอเค...", "โนโนโน...")
        condition_on_previous_text=use_prev_text,
        # Context
        initial_prompt=prompt if prompt else None,
        # Language
        language=language,  # None = auto-detect
        # Word timestamps
        word_timestamps=True,
        # Anti-hallucination thresholds
        compression_ratio_threshold=compression_thresh,
        log_prob_threshold=log_prob_thresh,
        no_speech_threshold=no_speech_thresh,
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

        # Fallback with even more relaxed settings
        fallback_log_prob = -1.0 if is_thai else -0.8
        fallback_temp = (0.0, 0.2, 0.4, 0.6) if is_thai else 0.0
        logger.info(f"Fallback: VAD=False, relaxed thresholds, thai={is_thai}")
        segments_iter2, info2 = model.transcribe(
            actual_audio_path,
            vad_filter=False,
            beam_size=beam,
            best_of=best,
            temperature=fallback_temp,
            condition_on_previous_text=use_prev_text,
            initial_prompt=prompt if prompt else None,
            language=language,
            word_timestamps=True,
            compression_ratio_threshold=2.4,
            log_prob_threshold=fallback_log_prob,
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

    # --- Post-processing: Thai word corrections (dictionary) ---
    if is_thai and on_progress:
        on_progress(73, "Applying Thai word corrections...")

    # Build initial result segments (before AI correction)
    result_segments: list[TranscriptionSegment] = []
    seg_count = 0

    for seg in clean_segments:
        seg_text = seg.text.strip()

        # Apply dictionary-based Thai corrections
        if is_thai:
            seg_text = _apply_thai_corrections(seg_text)

        words: list[WordTimestamp] = []
        if seg.words:
            for w in seg.words:
                word_text = w.word.strip()
                if is_thai:
                    word_text = _apply_thai_corrections(word_text)
                words.append(WordTimestamp(
                    word=word_text,
                    start=round(w.start, 3),
                    end=round(w.end, 3),
                    confidence=round(w.probability, 3),
                ))

        result_segments.append(TranscriptionSegment(
            id=seg_count,
            text=seg_text,
            start=round(seg.start, 3),
            end=round(seg.end, 3),
            words=words,
        ))
        seg_count += 1

        if on_progress and total_duration > 0:
            pct = min(74, int(70 + (seg.end / total_duration) * 4))
            on_progress(pct, f"Segment {seg_count}: {seg_text[:40]}...")

    # --- Post-processing: Gemini AI correction for Thai ---
    if is_thai and result_segments:
        try:
            from gemini_correction import is_available, correct_thai_transcription
            import asyncio

            if is_available():
                if on_progress:
                    on_progress(76, "🤖 AI correcting Thai text with Gemini...")

                logger.info("Starting Gemini AI Thai correction...")

                # Extract texts for correction
                original_texts = [seg.text for seg in result_segments]

                # Run async correction in sync context
                loop = None
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass

                if loop and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        corrected_texts = pool.submit(
                            lambda: asyncio.run(
                                correct_thai_transcription(original_texts, on_progress)
                            )
                        ).result(timeout=90)
                else:
                    corrected_texts = asyncio.run(
                        correct_thai_transcription(original_texts, on_progress)
                    )

                # Apply corrections back to segments
                corrections_applied = 0
                for i, (seg, corrected) in enumerate(zip(result_segments, corrected_texts)):
                    if corrected != seg.text:
                        corrections_applied += 1
                        logger.info(f"  AI fix [{i}]: '{seg.text}' → '{corrected}'")

                        # Update segment text
                        seg.text = corrected

                        # Rebuild words from corrected text, preserving timing
                        new_words_text = corrected.strip().split()
                        if new_words_text and seg.words:
                            duration = seg.end - seg.start
                            time_per_word = duration / len(new_words_text)
                            seg.words = [
                                WordTimestamp(
                                    word=w,
                                    start=round(seg.start + (j * time_per_word), 3),
                                    end=round(seg.start + ((j + 1) * time_per_word), 3),
                                    confidence=0.95,
                                )
                                for j, w in enumerate(new_words_text)
                            ]

                logger.info(f"Gemini AI correction: {corrections_applied}/{len(result_segments)} segments fixed")

                if on_progress:
                    on_progress(85, f"AI corrected {corrections_applied} segments")
            else:
                logger.info("Gemini API key not set — skipping AI correction")
        except Exception as e:
            logger.warning(f"Gemini AI correction failed (non-fatal): {e}")
            # Continue with uncorrected segments

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
