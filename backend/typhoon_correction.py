"""
Typhoon AI Post-Correction Service for Thai song transcription.

After Whisper transcribes audio, this service sends the raw Thai text
to Typhoon (Thai LLM by SCB 10X) to correct common Thai spelling/consonant errors.

KEY FEATURE: Typhoon tries to IDENTIFY the song first, then corrects
based on actual known lyrics — far more accurate than rule-based fixes.

Typhoon is a Thai-specialized LLM with deep knowledge of Thai language,
culture, and music — superior to general-purpose models for Thai correction.

API: OpenAI-compatible at https://api.opentyphoon.ai/v1
Requires: TYPHOON_API_KEY environment variable.
"""
from __future__ import annotations
import json
import logging
import os
import re
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)


def _load_api_key() -> str:
    """Load API key from env var or .env file."""
    key = os.environ.get("TYPHOON_API_KEY", "")
    if not key:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith("TYPHOON_API_KEY="):
                        key = line.strip().split("=", 1)[1].strip()
                        break
    return key


TYPHOON_API_KEY = _load_api_key()

# Typhoon API endpoint — OpenAI-compatible
_TYPHOON_BASE_URL = "https://api.opentyphoon.ai/v1"
_TYPHOON_CHAT_URL = f"{_TYPHOON_BASE_URL}/chat/completions"

# Model to use — best quality Thai model
_TYPHOON_MODEL = "typhoon-v2.5-30b-a3b-instruct"

_CORRECTION_SYSTEM_PROMPT = """\
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
"""

# Retry settings
_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 5, 10]  # seconds
_CHUNK_SIZE = 15  # Max segments per API call


def is_available() -> bool:
    """Check if Typhoon API key is configured."""
    return bool(TYPHOON_API_KEY) and TYPHOON_API_KEY not in (
        "YOUR_TYPHOON_API_KEY_HERE",
        "your_typhoon_api_key_here",
    )


def _call_typhoon(
    system_prompt: str,
    user_prompt: str,
    retry_count: int = 0,
) -> dict | None:
    """
    Call Typhoon chat completions API with retry logic.

    Uses OpenAI-compatible format:
    POST /v1/chat/completions
    Authorization: Bearer <key>
    """
    import urllib.request
    import urllib.error

    request_body = {
        "model": _TYPHOON_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "top_p": 0.8,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }

    try:
        req_data = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            _TYPHOON_CHAT_URL,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TYPHOON_API_KEY}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")

        if e.code == 429 and retry_count < _MAX_RETRIES:
            delay = _RETRY_DELAYS[min(retry_count, len(_RETRY_DELAYS) - 1)]
            logger.warning(
                f"Typhoon 429 rate limit — retrying in {delay}s "
                f"(attempt {retry_count + 1}/{_MAX_RETRIES})"
            )
            time.sleep(delay)
            return _call_typhoon(system_prompt, user_prompt, retry_count + 1)

        logger.error(f"Typhoon API HTTP {e.code}: {error_body[:300]}")
        return None

    except urllib.error.URLError as e:
        logger.error(f"Typhoon connection error: {e}")
        return None
    except Exception as e:
        logger.error(f"Typhoon call failed: {e}")
        return None


def _parse_response(result: dict) -> tuple[str | None, str | None, list[str] | None]:
    """Parse Typhoon response → (song_name, artist, corrected_lines)."""
    try:
        choices = result.get("choices", [])
        if not choices:
            return None, None, None

        message = choices[0].get("message", {})
        text = message.get("content", "").strip()
        logger.info(f"Typhoon raw response: {text[:300]}")

        # Parse JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                logger.warning("Could not parse Typhoon JSON response")
                return None, None, None

        song = data.get("song")
        artist = data.get("artist")
        corrected = data.get("corrected")

        if isinstance(corrected, list):
            return song, artist, corrected

        return song, artist, None

    except Exception as e:
        logger.error(f"Failed to parse Typhoon response: {e}")
        return None, None, None


async def correct_thai_transcription(
    segment_texts: list[str],
    on_progress: Optional[Callable] = None,
    reference: str = "",
) -> list[str]:
    """
    Send Thai transcription segments to Typhoon for correction.

    Args:
        segment_texts: Raw Whisper transcription texts
        on_progress: Progress callback
        reference: Reference lyrics from lyrics search

    Returns corrected texts (same length as input).
    """
    if not is_available():
        logger.warning("TYPHOON_API_KEY not set — skipping AI correction")
        return segment_texts

    if not segment_texts:
        return segment_texts

    if on_progress:
        on_progress(76, "🤖 AI correcting lyrics (Typhoon)...")

    total = len(segment_texts)
    logger.info(f"Sending {total} segments to Typhoon (ref={len(reference)} chars)")

    # For short transcriptions, send all at once
    if total <= _CHUNK_SIZE:
        return _correct_chunk(segment_texts, on_progress, reference)

    # For long transcriptions, process in chunks
    result = []
    for i in range(0, total, _CHUNK_SIZE):
        chunk = segment_texts[i : i + _CHUNK_SIZE]
        chunk_num = i // _CHUNK_SIZE + 1
        total_chunks = (total + _CHUNK_SIZE - 1) // _CHUNK_SIZE

        if on_progress:
            pct = 76 + int((i / total) * 8)
            on_progress(pct, f"🤖 AI correcting chunk {chunk_num}/{total_chunks}...")

        corrected_chunk = _correct_chunk(chunk, None, reference)
        result.extend(corrected_chunk)

    if on_progress:
        on_progress(85, "AI correction complete")

    return result


def _correct_chunk(
    texts: list[str],
    on_progress: Optional[Callable] = None,
    reference: str = "",
) -> list[str]:
    """Correct a chunk of segment texts via Typhoon."""
    # Build numbered user prompt
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    user_prompt = ""
    if reference:
        user_prompt += f"## เนื้อเพลงอ้างอิง (จากการค้นหา):\n{reference}\n\n"
    user_prompt += "## เนื้อที่ต้องแก้ (จาก Whisper):\n" + numbered

    # Call Typhoon
    result = _call_typhoon(_CORRECTION_SYSTEM_PROMPT, user_prompt)
    if not result:
        logger.warning("Typhoon returned no result — using original texts")
        return texts

    song, artist, corrected = _parse_response(result)

    if song:
        logger.info(f"🎵 Typhoon identified song: '{song}' by '{artist or 'unknown'}'")
    else:
        logger.info("Typhoon could not identify the song")

    if not corrected:
        logger.warning("Typhoon returned no corrections")
        return texts

    # Validate length
    if len(corrected) != len(texts):
        logger.warning(
            f"Typhoon returned {len(corrected)} lines, expected {len(texts)} — "
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

    logger.info(f"Typhoon correction: {changes}/{len(texts)} segments changed")

    if on_progress and song:
        on_progress(82, f"🎵 Song: {song} — {changes} segments corrected")
    elif on_progress:
        on_progress(82, f"AI corrected {changes} segments")

    return result_texts
