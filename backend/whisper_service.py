"""
ASR Service — Speech-to-text using Typhoon ASR API.

Replaces local faster-whisper with the Typhoon ASR endpoint.
Supports word-level timestamps and Thai-optimized transcription.
"""
from __future__ import annotations
import logging
import os
import re
import subprocess
import json
import requests
from typing import Optional, Callable
from models import TranscriptionResult, TranscriptionSegment, WordTimestamp, ASRModel
from typhoon_correction import TYPHOON_API_KEY

logger = logging.getLogger(__name__)

# Cache for extracted audio files
_audio_cache = {}


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
        # Strategy 1: Standard PCM WAV
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

    logger.warning("All ffmpeg strategies failed — returning original video path")
    return input_path


def _is_hallucinated_segment(text: str) -> bool:
    """Detect if a segment is a hallucination using n-gram frequency analysis."""
    text = text.strip()
    if not text:
        return True
    if len(text) <= 1:
        return True

    clean = re.sub(r'\s+', '', text)
    text_len = len(clean)

    if text_len < 6:
        return False

    for ngram_len in range(1, min(12, text_len // 2 + 1)):
        ngram_counts: dict[str, int] = {}
        for i in range(text_len - ngram_len + 1):
            ngram = clean[i:i + ngram_len]
            ngram_counts[ngram] = ngram_counts.get(ngram, 0) + 1

        if not ngram_counts:
            continue

        top_ngram = max(ngram_counts, key=ngram_counts.get)  # type: ignore
        top_count = ngram_counts[top_ngram]
        coverage = (top_count * ngram_len) / text_len

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
        if lower_text == phrase or (len(lower_text) < len(phrase) + 10 and phrase in lower_text):
            logger.info(f"Known hallucination phrase: '{text[:60]}'")
            return True

    return False


def _filter_hallucinations(segments: list[TranscriptionSegment]) -> list[TranscriptionSegment]:
    """Post-process segments to remove hallucinated ones."""
    if not segments:
        return segments

    filtered = []
    prev_text = ""

    for seg in segments:
        text = seg.text.strip() if hasattr(seg, 'text') else ""

        if _is_hallucinated_segment(text):
            logger.info(f"Removing hallucinated segment [{seg.start:.1f}-{seg.end:.1f}]: '{text[:80]}'")
            continue

        if text == prev_text and text:
            logger.info(f"Removing duplicate segment [{seg.start:.1f}-{seg.end:.1f}]: '{text[:60]}'")
            continue

        filtered.append(seg)
        prev_text = text

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


_THAI_CORRECTIONS: dict[str, str] = {
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
    "จว่า": "กว่า",
    "ท่อง": "ต้อง",
    "เทา": "เท่า",
    "เท่าไร่": "เท่าไหร่",
    "เทาไหร่": "เท่าไหร่",
    "เท่าหร่": "เท่าไหร่",
    "คลับ": "กลับ",
    "คลัว": "กลัว",
    "ม่าก": "มาก",
    "ร้อง": "ร้อง",
    "สะ ออน": "สะออน",
    "หัว ใจ": "หัวใจ",
    "คิด ถึง": "คิดถึง",
    "ร้อง ไห้": "ร้องไห้",
    "ทำ ไม": "ทำไม",
    "เท่า ไหร่": "เท่าไหร่",
}


def _apply_thai_corrections(text: str) -> str:
    """Apply Thai word corrections."""
    result = text
    for wrong, correct in _THAI_CORRECTIONS.items():
        result = result.replace(wrong, correct)
    return result


def transcribe_audio(
    audio_path: str,
    model_size: ASRModel = ASRModel.TYPHOON_ASR,
    language: Optional[str] = None,
    initial_prompt: Optional[str] = None,
    hotwords: Optional[list[str]] = None,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> TranscriptionResult:
    """
    Transcribe audio using Typhoon ASR API.
    """
    if not TYPHOON_API_KEY:
        raise ValueError("TYPHOON_API_KEY is not set")

    if on_progress:
        on_progress(5, "Extracting audio from video...")

    actual_audio_path = _extract_audio_wav(audio_path)

    is_thai = language and language.lower() == "th"
    # For Typhoon ASR, we'll assume it handles Thai by default, especially typhoon-isan-asr-realtime

    if on_progress:
        on_progress(15, f"Calling Typhoon ASR API ({model_size.value})...")

    # Call Typhoon ASR API
    api_url = "https://api.opentyphoon.ai/v1/audio/transcriptions"
    
    # We must send standard form-data
    headers = {
        "Authorization": f"Bearer {TYPHOON_API_KEY}"
    }
    
    data = {
        "model": model_size.value,
        "response_format": "verbose_json",
        "timestamp_granularities[]": "word",
    }
    
    if initial_prompt:
        data["prompt"] = initial_prompt
    if language:
        data["language"] = language

    try:
        with open(actual_audio_path, "rb") as f:
            files = {"file": (os.path.basename(actual_audio_path), f, "audio/wav")}
            response = requests.post(api_url, headers=headers, data=data, files=files, timeout=300)
            
        if response.status_code != 200:
            logger.error(f"Typhoon ASR Error: {response.text}")
            raise Exception(f"Typhoon ASR API returned status {response.status_code}")
            
        result_json = response.json()
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise e
        
    if on_progress:
        on_progress(60, "Processing ASR results...")

    # Parse verbose_json response
    raw_segments: list[TranscriptionSegment] = []
    
    # Extract timestamps from response
    words_data = result_json.get("timestamps", {}).get("word", [])
    
    if not words_data:
        logger.warning("No words found in Typhoon ASR response.")
        
    # Group words into segments (since the API doesn't seem to return a 'segment' array natively or we can just build our own from words)
    # Actually, let's check if there is a 'segment' array
    segment_data = result_json.get("timestamps", {}).get("segment", [])
    
    if segment_data:
        # If API gives segments, use them
        for i, s in enumerate(segment_data):
            start = s.get("start", 0)
            end = s.get("end", 0)
            text = s.get("text", "")
            
            # Find words that fall in this segment
            seg_words = []
            for w in words_data:
                if w.get("start", 0) >= start and w.get("end", 0) <= end:
                    seg_words.append(WordTimestamp(
                        word=w.get("text", ""),
                        start=w.get("start", 0),
                        end=w.get("end", 0),
                        confidence=w.get("confidence", 1.0)
                    ))
            
            raw_segments.append(TranscriptionSegment(
                id=i,
                text=text,
                start=start,
                end=end,
                words=seg_words
            ))
    else:
        # Build fake segments from words (e.g., group by pauses > 0.5s)
        current_segment_words = []
        seg_id = 0
        
        for w in words_data:
            if not current_segment_words:
                current_segment_words.append(w)
                continue
                
            last_word = current_segment_words[-1]
            # If gap > 0.5s or we have > 10 words, start new segment
            if w.get("start", 0) - last_word.get("end", 0) > 0.5 or len(current_segment_words) >= 15:
                # Close segment
                start = current_segment_words[0].get("start", 0)
                end = current_segment_words[-1].get("end", 0)
                text = " ".join(cw.get("text", "") for cw in current_segment_words)
                
                raw_segments.append(TranscriptionSegment(
                    id=seg_id,
                    text=text,
                    start=start,
                    end=end,
                    words=[WordTimestamp(word=cw.get("text", ""), start=cw.get("start", 0), end=cw.get("end", 0), confidence=cw.get("confidence", 1.0)) for cw in current_segment_words]
                ))
                seg_id += 1
                current_segment_words = [w]
            else:
                current_segment_words.append(w)
                
        if current_segment_words:
            start = current_segment_words[0].get("start", 0)
            end = current_segment_words[-1].get("end", 0)
            text = " ".join(cw.get("text", "") for cw in current_segment_words)
            raw_segments.append(TranscriptionSegment(
                id=seg_id,
                text=text,
                start=start,
                end=end,
                words=[WordTimestamp(word=cw.get("text", ""), start=cw.get("start", 0), end=cw.get("end", 0), confidence=cw.get("confidence", 1.0)) for cw in current_segment_words]
            ))

    logger.info(f"Raw transcription: {len(raw_segments)} segments")

    if on_progress:
        on_progress(70, "Filtering hallucinations...")

    clean_segments = _filter_hallucinations(raw_segments)
    
    # Process Thai word corrections
    if is_thai and on_progress:
        on_progress(73, "Applying Thai word corrections...")

    result_segments: list[TranscriptionSegment] = []
    for i, seg in enumerate(clean_segments):
        seg_text = seg.text.strip()
        if is_thai:
            seg_text = _apply_thai_corrections(seg_text)

        words: list[WordTimestamp] = []
        for w in seg.words:
            word_text = w.word.strip()
            if is_thai:
                word_text = _apply_thai_corrections(word_text)
            words.append(WordTimestamp(
                word=word_text,
                start=w.start,
                end=w.end,
                confidence=w.confidence,
            ))

        result_segments.append(TranscriptionSegment(
            id=i,
            text=seg_text,
            start=seg.start,
            end=seg.end,
            words=words,
        ))

    # PASS 2 & 3: Lyrics Search and Typhoon LLM Correction
    reference_lyrics = None
    song_info = ""
    
    if is_thai and result_segments:
        if on_progress:
            on_progress(75, "🔍 Searching for song lyrics online...")

        whisper_texts = [seg.text for seg in result_segments]
        
        try:
            from lyrics_search import search_lyrics, search_lyrics_with_typhoon

            search_result = search_lyrics(whisper_texts)
            if not search_result:
                search_result = search_lyrics_with_typhoon(whisper_texts)

            if search_result and search_result.get("lyrics"):
                reference_lyrics = search_result["lyrics"]
                song_info = search_result.get("song", "") or ""
                if on_progress:
                    on_progress(78, f"🎵 Found: {song_info} ({len(reference_lyrics)} lines)")
        except Exception as e:
            logger.warning(f"Pass 2 lyrics search failed: {e}")

        try:
            from typhoon_correction import is_available, correct_thai_transcription
            import asyncio

            if is_available():
                if on_progress:
                    on_progress(80, "🤖 Typhoon correcting Thai text...")

                original_texts = [seg.text for seg in result_segments]
                reference = " ".join(reference_lyrics) if reference_lyrics else ""

                try:
                    loop = asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        corrected_texts = pool.submit(
                            lambda: asyncio.run(
                                correct_thai_transcription(original_texts, on_progress, reference)
                            )
                        ).result(timeout=90)
                except RuntimeError:
                    corrected_texts = asyncio.run(
                        correct_thai_transcription(original_texts, on_progress, reference)
                    )

                for i, (seg, corrected) in enumerate(zip(result_segments, corrected_texts)):
                    if corrected != seg.text:
                        seg.text = corrected
                        new_words = corrected.strip().split()
                        if new_words:
                            dur = seg.end - seg.start
                            tpw = dur / len(new_words)
                            seg.words = [
                                WordTimestamp(
                                    word=w, start=round(seg.start + j*tpw, 3),
                                    end=round(seg.start + (j+1)*tpw, 3),
                                    confidence=0.95,
                                ) for j, w in enumerate(new_words)
                            ]
        except Exception as e:
            logger.warning(f"Pass 3 correction failed: {e}")

    # Cleanup extracted audio if we created a temp one
    if actual_audio_path != audio_path and os.path.exists(actual_audio_path):
        try:
            os.remove(actual_audio_path)
        except Exception:
            pass

    duration = result_segments[-1].end if result_segments else 0.0
    detected_language = result_json.get("language", language or "en")

    if on_progress:
        on_progress(100, f"Done — {len(result_segments)} segments")

    return TranscriptionResult(
        segments=result_segments,
        language=detected_language,
        duration=duration,
    )
