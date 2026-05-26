"""
Gemini AI Post-Correction Service for Thai song transcription.

After Whisper transcribes audio, this service sends the raw Thai text
to Google Gemini to correct common Thai spelling/consonant errors.

KEY FEATURE: Gemini tries to IDENTIFY the song first, then corrects
based on actual known lyrics — far more accurate than rule-based fixes.

Requires: GEMINI_API_KEY environment variable.
"""
from __future__ import annotations
import json
import logging
import os
import re
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Gemini API endpoint — using gemini-2.5-flash for best quality
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

_CORRECTION_PROMPT = """\
คุณเป็นผู้เชี่ยวชาญเนื้อเพลงไทย มีความรู้เพลงไทยทุกยุคทุกสมัย

## งานของคุณ
คุณจะได้รับเนื้อเพลงไทยที่ถอดมาจาก AI (Whisper) ซึ่งมีข้อผิดพลาดมาก โดยเฉพาะ:
- พยัญชนะสับสน: ช↔ซ↔ส, ก↔ค, ท↔ต, พ↔ฟ, กร→ร (กว่า→ว่า)
- ทั้งวลีผิด: เช่น "ชอกช้ำ" ถูกถอดเป็น "ชอบทำ", "หลอกลวง" เป็น "ลองรวม"
- เนื้อเพลงผิดทั้งประโยค (Whisper ได้ยินคำอื่น)
- คำเกินจากช่วงดนตรี (hallucination)
- วรรณยุกต์ผิด: ไม้เอก/โท หาย หรือเกิน
- คำติดกัน/แยกผิด: "ทำนอง"→"ท้อง", "เจ้ากรรม"→"เจ้ากลับ"

## ขั้นตอน
1. **ระบุเพลง**: พยายามระบุชื่อเพลงและศิลปินจากเนื้อเพลงที่ถอดมา
2. **ถ้าระบุได้**: แก้เนื้อเพลงให้ตรงกับเนื้อเพลงจริงของเพลงนั้น
3. **ถ้าระบุไม่ได้**: แก้ตามหลักภาษาไทยและบริบทของเพลง

## กฎสำคัญ
1. จำนวนบรรทัดต้องเท่าเดิม (สำคัญมาก!)
2. ถ้าบรรทัดเป็นดนตรี/เงียบ (ข้อความสั้นมากหรือไม่ใช่เนื้อเพลง) ให้คงเดิม
3. ตอบเป็น JSON object เท่านั้น ในรูปแบบ:
{"song": "ชื่อเพลง (ถ้าระบุได้)", "artist": "ศิลปิน (ถ้าระบุได้)", "corrected": ["บรรทัด1", "บรรทัด2", ...]}

## เนื้อเพลงที่ต้องแก้:
"""

# Retry settings
_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 5, 10]  # seconds
_CHUNK_SIZE = 15  # Max segments per Gemini call


def is_available() -> bool:
    """Check if Gemini API key is configured."""
    return bool(GEMINI_API_KEY) and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE"


def _call_gemini(prompt: str, retry_count: int = 0) -> dict | None:
    """Call Gemini API with retry logic for rate limits."""
    import urllib.request
    import urllib.error

    request_body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.8,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }

    url = f"{_GEMINI_URL}?key={GEMINI_API_KEY}"

    try:
        req_data = json.dumps(request_body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")

        if e.code == 429 and retry_count < _MAX_RETRIES:
            delay = _RETRY_DELAYS[min(retry_count, len(_RETRY_DELAYS) - 1)]
            logger.warning(
                f"Gemini 429 rate limit — retrying in {delay}s "
                f"(attempt {retry_count + 1}/{_MAX_RETRIES})"
            )
            time.sleep(delay)
            return _call_gemini(prompt, retry_count + 1)

        logger.error(f"Gemini API HTTP {e.code}: {error_body[:300]}")
        return None

    except urllib.error.URLError as e:
        logger.error(f"Gemini connection error: {e}")
        return None
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        return None


def _parse_response(result: dict) -> tuple[str | None, str | None, list[str] | None]:
    """Parse Gemini response → (song_name, artist, corrected_lines)."""
    try:
        candidates = result.get("candidates", [])
        if not candidates:
            return None, None, None

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            return None, None, None

        text = parts[0].get("text", "").strip()
        logger.info(f"Gemini raw response: {text[:300]}")

        # Parse JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                logger.warning("Could not parse Gemini JSON response")
                return None, None, None

        song = data.get("song")
        artist = data.get("artist")
        corrected = data.get("corrected")

        if isinstance(corrected, list):
            return song, artist, corrected

        return song, artist, None

    except Exception as e:
        logger.error(f"Failed to parse Gemini response: {e}")
        return None, None, None


async def correct_thai_transcription(
    segment_texts: list[str],
    on_progress: Optional[Callable] = None,
) -> list[str]:
    """
    Send Thai transcription segments to Gemini for correction.

    The AI will try to identify the song and correct based on real lyrics.
    Falls back to language-rule corrections if song is not recognized.

    Returns corrected texts (same length as input).
    """
    if not is_available():
        logger.warning("GEMINI_API_KEY not set — skipping AI correction")
        return segment_texts

    if not segment_texts:
        return segment_texts

    if on_progress:
        on_progress(76, "🤖 AI identifying song and correcting lyrics...")

    total = len(segment_texts)
    logger.info(f"Sending {total} segments to Gemini for Thai correction")

    # For short transcriptions, send all at once
    if total <= _CHUNK_SIZE:
        return _correct_chunk(segment_texts, on_progress)

    # For long transcriptions, process in chunks
    result = []
    for i in range(0, total, _CHUNK_SIZE):
        chunk = segment_texts[i : i + _CHUNK_SIZE]
        chunk_num = i // _CHUNK_SIZE + 1
        total_chunks = (total + _CHUNK_SIZE - 1) // _CHUNK_SIZE

        if on_progress:
            pct = 76 + int((i / total) * 8)
            on_progress(pct, f"🤖 AI correcting chunk {chunk_num}/{total_chunks}...")

        corrected_chunk = _correct_chunk(chunk, None)
        result.extend(corrected_chunk)

    if on_progress:
        on_progress(85, "AI correction complete")

    return result


def _correct_chunk(
    texts: list[str],
    on_progress: Optional[Callable] = None,
) -> list[str]:
    """Correct a chunk of segment texts via Gemini."""
    # Build numbered prompt
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    full_prompt = _CORRECTION_PROMPT + numbered

    # Call Gemini
    result = _call_gemini(full_prompt)
    if not result:
        logger.warning("Gemini returned no result — using original texts")
        return texts

    song, artist, corrected = _parse_response(result)

    if song:
        logger.info(f"🎵 Gemini identified song: '{song}' by '{artist or 'unknown'}'")
    else:
        logger.info("Gemini could not identify the song")

    if not corrected:
        logger.warning("Gemini returned no corrections")
        return texts

    # Validate length
    if len(corrected) != len(texts):
        logger.warning(
            f"Gemini returned {len(corrected)} lines, expected {len(texts)} — "
            f"using partial corrections"
        )
        result_texts = list(texts)
        for i in range(min(len(corrected), len(texts))):
            if isinstance(corrected[i], str) and corrected[i].strip():
                result_texts[i] = corrected[i].strip()
        return result_texts

    # Apply corrections
    result_texts = []
    changes = 0
    for i, (original, fixed) in enumerate(zip(texts, corrected)):
        if isinstance(fixed, str) and fixed.strip():
            fixed = fixed.strip()
            if fixed != original:
                changes += 1
                logger.info(f"  AI fix [{i}]: '{original}' → '{fixed}'")
            result_texts.append(fixed)
        else:
            result_texts.append(original)

    logger.info(f"Gemini correction: {changes}/{len(texts)} segments changed")

    if on_progress and song:
        on_progress(82, f"🎵 Song: {song} — {changes} segments corrected")
    elif on_progress:
        on_progress(82, f"AI corrected {changes} segments")

    return result_texts
