"""
Gemini Audio Scan — sends audio directly to Gemini to extract Thai lyrics.

Gemini can listen to audio and understand Thai songs much better than Whisper
because it has vast knowledge of Thai music. This module:

1. Extracts audio from video as MP3 (small file for upload)
2. Sends audio to Gemini with Thai lyrics prompt
3. Returns accurate lyrics text

The lyrics are then used to:
- Guide Whisper via initial_prompt (biases Whisper toward correct words)
- Replace Whisper's text while keeping its timestamps

Requires: GEMINI_API_KEY environment variable.
"""
from __future__ import annotations
import base64
import json
import logging
import os
import subprocess
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)

def _load_api_key() -> str:
    """Load API key from env var or .env file."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        key = line.strip().split("=", 1)[1].strip()
                        break
    return key

GEMINI_API_KEY = _load_api_key()

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

_SCAN_PROMPT = """\
คุณเป็นผู้เชี่ยวชาญเนื้อเพลงไทย ฟังเสียงเพลงนี้แล้วถอดเนื้อเพลงให้ถูกต้อง 100%

กฎ:
1. ถอดเนื้อเพลงภาษาไทยให้ถูกต้องทุกคำ ทุกพยัญชนะ ทุกวรรณยุกต์
2. ถ้าจำเพลงนี้ได้ ให้ใช้เนื้อเพลงจริงที่ถูกต้อง
3. แต่ละบรรทัดควรเป็นวลีหรือประโยคสั้นๆ (ไม่เกิน 2 วรรค)
4. ช่วงดนตรีบรรเลง (ไม่มีเสียงร้อง) ให้ข้าม ไม่ต้องเขียนอะไร
5. ตอบเป็น JSON object:
{"song": "ชื่อเพลง", "artist": "ศิลปิน", "lyrics": ["บรรทัด1", "บรรทัด2", ...]}
6. ถ้าไม่รู้ชื่อเพลง ให้ใส่ song: null, artist: null

ฟังเพลงแล้วถอดเนื้อเพลงให้ถูกต้อง:
"""

# Retry settings
_MAX_RETRIES = 3
_RETRY_DELAYS = [3, 8, 15]


def is_available() -> bool:
    """Check if Gemini API key is configured."""
    return bool(GEMINI_API_KEY) and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE"


def _extract_audio_mp3(video_path: str) -> Optional[str]:
    """Extract audio as MP3 for Gemini upload (much smaller than WAV)."""
    output = os.path.join(os.path.dirname(video_path), "_gemini_scan.mp3")

    strategies = [
        # Strategy 1: Proper MP3 encoding
        ["ffmpeg", "-y", "-i", video_path, "-vn",
         "-acodec", "libmp3lame", "-ab", "64k", "-ar", "16000", "-ac", "1",
         output],
        # Strategy 2: Copy audio stream as-is (fast, works if source is compatible)
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "copy",
         output.replace(".mp3", ".m4a")],
        # Strategy 3: Just extract as WAV (larger but works everywhere)
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1",
         output.replace(".mp3", ".wav")],
    ]

    for i, cmd in enumerate(strategies):
        try:
            target = cmd[-1]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and os.path.exists(target):
                size = os.path.getsize(target)
                if size > 1000:
                    size_mb = size / (1024 * 1024)
                    logger.info(f"Audio for Gemini (strategy {i+1}): {target} ({size_mb:.1f}MB)")
                    return target
                os.remove(target)
        except Exception as e:
            logger.info(f"Audio extract strategy {i+1} failed: {e}")

    logger.warning("Could not extract audio for Gemini scan")
    return None


def _get_mime_type(path: str) -> str:
    """Get MIME type from file extension."""
    ext = os.path.splitext(path)[1].lower()
    return {
        ".mp3": "audio/mp3",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }.get(ext, "audio/mpeg")


def _call_gemini_with_audio(audio_path: str, retry: int = 0) -> dict | None:
    """Send audio to Gemini and get response."""
    import urllib.request
    import urllib.error

    # Read and base64-encode the audio
    with open(audio_path, "rb") as f:
        audio_data = base64.b64encode(f.read()).decode("utf-8")

    mime = _get_mime_type(audio_path)
    size_mb = len(audio_data) * 3 / 4 / (1024 * 1024)
    logger.info(f"Sending audio to Gemini: {mime}, ~{size_mb:.1f}MB")

    body = {
        "contents": [{
            "parts": [
                {"text": _SCAN_PROMPT},
                {"inline_data": {"mime_type": mime, "data": audio_data}},
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.8,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }

    url = f"{_GEMINI_URL}?key={GEMINI_API_KEY}"

    try:
        req_data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # Longer timeout for audio processing
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))

    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        if e.code == 429 and retry < _MAX_RETRIES:
            delay = _RETRY_DELAYS[min(retry, len(_RETRY_DELAYS) - 1)]
            logger.warning(f"Gemini 429 — retry in {delay}s ({retry+1}/{_MAX_RETRIES})")
            time.sleep(delay)
            return _call_gemini_with_audio(audio_path, retry + 1)
        logger.error(f"Gemini HTTP {e.code}: {err[:300]}")
        return None
    except Exception as e:
        logger.error(f"Gemini audio call failed: {e}")
        return None


def scan_audio(
    video_path: str,
    on_progress: Optional[Callable] = None,
) -> dict | None:
    """
    Scan audio with Gemini to extract accurate Thai lyrics.

    Returns dict with keys:
    - song: str | None (identified song name)
    - artist: str | None (identified artist)
    - lyrics: list[str] (accurate lyrics lines)

    Returns None if scan fails.
    """
    if not is_available():
        logger.info("Gemini API not available — skipping audio scan")
        return None

    if on_progress:
        on_progress(5, "🤖 AI scanning audio with Gemini...")

    # Step 1: Extract audio as MP3
    audio_path = _extract_audio_mp3(video_path)
    if not audio_path:
        # Try sending video directly (Gemini supports video too)
        logger.info("Trying to send video directly to Gemini")
        audio_path = video_path

    if on_progress:
        on_progress(8, "🤖 Sending audio to Gemini for analysis...")

    # Step 2: Call Gemini
    result = _call_gemini_with_audio(audio_path)

    # Cleanup temp audio
    if audio_path != video_path and os.path.exists(audio_path):
        try:
            os.remove(audio_path)
        except Exception:
            pass

    if not result:
        logger.warning("Gemini audio scan returned no result")
        return None

    # Step 3: Parse response
    try:
        candidates = result.get("candidates", [])
        if not candidates:
            return None

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        logger.info(f"Gemini scan response: {text[:500]}")

        import re
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                return None

        song = data.get("song")
        artist = data.get("artist")
        lyrics = data.get("lyrics", [])

        if not isinstance(lyrics, list) or not lyrics:
            return None

        # Filter out empty lines
        lyrics = [line.strip() for line in lyrics if isinstance(line, str) and line.strip()]

        if song:
            logger.info(f"🎵 Gemini identified: '{song}' by '{artist}'")
        logger.info(f"🎵 Gemini extracted {len(lyrics)} lyric lines")

        if on_progress:
            msg = f"🎵 '{song}' — {len(lyrics)} lines" if song else f"🎵 {len(lyrics)} lyric lines found"
            on_progress(12, msg)

        return {"song": song, "artist": artist, "lyrics": lyrics}

    except Exception as e:
        logger.error(f"Failed to parse Gemini scan: {e}")
        return None
