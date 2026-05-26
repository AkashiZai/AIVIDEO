"""
Gemini AI Post-Correction Service for Thai transcription.

After Whisper transcribes audio, this service sends the raw Thai text
to Google Gemini to correct common Thai spelling/consonant errors.
This is especially effective for Thai songs where Whisper frequently
confuses similar-sounding consonants (ช/ซ/ส, ก/ค, etc.).

Requires: GEMINI_API_KEY environment variable.
"""
from __future__ import annotations
import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Gemini API endpoint
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

_CORRECTION_PROMPT = """\
คุณเป็นผู้เชี่ยวชาญภาษาไทยและเนื้อเพลงไทย คุณจะได้รับเนื้อเพลงไทยที่ถอดมาจาก AI (Whisper) ซึ่งมีข้อผิดพลาดเรื่องการสะกดคำ โดยเฉพาะ:
- พยัญชนะสับสน: ช↔ซ, ส↔ซ, ก↔ค, ท↔ต, พ↔ฟ เป็นต้น
- สระผิด: เช่น สระอา↔สระอะ, ไอ↔ใอ
- วรรณยุกต์ผิด: เช่น ไม่มีไม้เอก/โท หรือมีเกิน
- คำหาย: เช่น "กว่า" กลายเป็น "ว่า" (หาย ก)
- คำติดกัน: เช่น "ชอกช้ำ" กลายเป็น "ชอบทำ"

กฎ:
1. แก้ไขเฉพาะการสะกดคำที่ผิดเท่านั้น ไม่เพิ่มหรือลดจำนวนบรรทัด
2. คงจำนวนบรรทัดเท่าเดิม (สำคัญมาก!)
3. ไม่เปลี่ยนความหมายโดยรวม
4. ถ้าไม่แน่ใจ ให้คงคำเดิมไว้
5. ตอบเฉพาะเนื้อเพลงที่แก้แล้ว บรรทัดต่อบรรทัด ไม่ต้องมีคำอธิบาย
6. ตอบในรูปแบบ JSON array ของ strings เท่านั้น เช่น ["บรรทัด1", "บรรทัด2"]

เนื้อเพลงที่ต้องแก้ (แต่ละบรรทัดคือ 1 segment):
"""


def is_available() -> bool:
    """Check if Gemini API key is configured."""
    return bool(GEMINI_API_KEY)


async def correct_thai_transcription(
    segment_texts: list[str],
    on_progress: Optional[callable] = None,
) -> list[str]:
    """
    Send Thai transcription segments to Gemini for spelling correction.
    
    Args:
        segment_texts: List of segment text strings from Whisper.
        on_progress: Optional callback (pct, message).
    
    Returns:
        List of corrected text strings, same length as input.
        If correction fails, returns the original texts.
    """
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set — skipping AI correction")
        return segment_texts

    if not segment_texts:
        return segment_texts

    import urllib.request
    import urllib.error

    # Build the prompt with numbered lines for clarity
    numbered_lines = "\n".join(
        f"{i+1}. {text}" for i, text in enumerate(segment_texts)
    )
    full_prompt = _CORRECTION_PROMPT + numbered_lines

    # Build Gemini API request
    request_body = {
        "contents": [
            {
                "parts": [
                    {"text": full_prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,  # Low temperature for precise corrections
            "topP": 0.8,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        }
    }

    url = f"{_GEMINI_URL}?key={GEMINI_API_KEY}"

    try:
        if on_progress:
            on_progress(78, "AI correcting Thai text...")

        logger.info(f"Sending {len(segment_texts)} segments to Gemini for Thai correction")

        req_data = json.dumps(request_body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))

        # Parse Gemini response
        candidates = result.get("candidates", [])
        if not candidates:
            logger.warning("Gemini returned no candidates")
            return segment_texts

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            logger.warning("Gemini returned no parts")
            return segment_texts

        response_text = parts[0].get("text", "").strip()
        logger.info(f"Gemini raw response: {response_text[:200]}")

        # Parse the JSON array response
        try:
            corrected = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON array from response
            match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if match:
                corrected = json.loads(match.group())
            else:
                # Fallback: split by newlines and strip numbering
                lines = response_text.strip().split("\n")
                corrected = []
                for line in lines:
                    # Remove numbering like "1. " or "1) "
                    clean = re.sub(r'^\d+[\.\)]\s*', '', line.strip())
                    if clean:
                        corrected.append(clean)

        if not isinstance(corrected, list):
            logger.warning(f"Gemini response is not a list: {type(corrected)}")
            return segment_texts

        # Validate: must have same number of segments
        if len(corrected) != len(segment_texts):
            logger.warning(
                f"Gemini returned {len(corrected)} lines but expected {len(segment_texts)} — "
                f"using partial correction"
            )
            # Use corrections for matching indices, keep original for rest
            result_texts = list(segment_texts)
            for i in range(min(len(corrected), len(segment_texts))):
                if isinstance(corrected[i], str) and corrected[i].strip():
                    result_texts[i] = corrected[i].strip()
            return result_texts

        # Apply corrections
        result_texts = []
        changes = 0
        for i, (original, fixed) in enumerate(zip(segment_texts, corrected)):
            if isinstance(fixed, str) and fixed.strip():
                fixed = fixed.strip()
                if fixed != original:
                    changes += 1
                    logger.info(f"  Corrected [{i}]: '{original}' → '{fixed}'")
                result_texts.append(fixed)
            else:
                result_texts.append(original)

        logger.info(f"Gemini correction: {changes}/{len(segment_texts)} segments changed")

        if on_progress:
            on_progress(82, f"AI corrected {changes} segments")

        return result_texts

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error(f"Gemini API HTTP error {e.code}: {error_body[:300]}")
        return segment_texts
    except urllib.error.URLError as e:
        logger.error(f"Gemini API connection error: {e}")
        return segment_texts
    except Exception as e:
        logger.error(f"Gemini correction failed: {e}")
        return segment_texts
