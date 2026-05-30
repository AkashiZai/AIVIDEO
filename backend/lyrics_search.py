"""
Thai Lyrics Search — find correct song lyrics from the web.

Instead of relying on Gemini audio processing (expensive, rate-limited),
this module searches Thai lyrics websites to find the correct lyrics
for a song identified from Whisper's rough transcription.

Flow:
1. Take rough text from Whisper
2. Search the web for matching Thai song lyrics
3. Return accurate lyrics for comparison/correction

No API key needed — uses free web search.
"""
from __future__ import annotations
import json
import logging
import os
import re
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

# Thai lyrics websites to search
_LYRICS_SITES = [
    "siamzone.com",
    "sanook.com",
    "kapook.com",
    "songsue.co",
    "deezer.com",
]

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class _TextExtractor(HTMLParser):
    """Simple HTML parser that extracts text content."""
    def __init__(self):
        super().__init__()
        self.texts: list[str] = []
        self._skip = False
        self._skip_tags = {"script", "style", "meta", "link", "head"}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.texts.append(text)


def _fetch_url(url: str, timeout: int = 15) -> str | None:
    """Fetch URL content as text."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
        return None


def _search_duckduckgo(query: str) -> list[dict]:
    """Search DuckDuckGo HTML and extract result URLs and titles."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    html = _fetch_url(url, timeout=10)
    if not html:
        return []

    results = []
    # Extract result links from DuckDuckGo HTML
    # Pattern: <a class="result__a" href="...">title</a>
    pattern = r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)'
    for match in re.finditer(pattern, html):
        href = match.group(1)
        title = match.group(2).strip()
        # DuckDuckGo wraps URLs in a redirect
        if "uddg=" in href:
            real_url = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
        else:
            real_url = href
        results.append({"url": real_url, "title": title})

    return results[:10]


def _extract_lyrics_from_html(html: str) -> list[str]:
    """Extract lyrics text from a lyrics page HTML."""
    lyrics_lines: list[str] = []

    # Strategy 1: Look for common lyrics containers
    # Many Thai lyrics sites use <pre>, <div class="lyrics">, etc.
    patterns = [
        # Pre-formatted lyrics
        r'<pre[^>]*>(.*?)</pre>',
        # Common lyrics div classes
        r'<div[^>]*class="[^"]*lyric[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*song[^"]*text[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*content[^"]*lyric[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*id="[^"]*lyric[^"]*"[^>]*>(.*?)</div>',
        # Sanook music specific
        r'<div[^>]*class="[^"]*desc[^"]*"[^>]*>(.*?)</div>',
        # SiamZone specific
        r'<div[^>]*class="[^"]*lyrics_detail[^"]*"[^>]*>(.*?)</div>',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        for match in matches:
            # Clean HTML tags from the match
            clean = re.sub(r'<br\s*/?\s*>', '\n', match)
            clean = re.sub(r'<[^>]+>', '', clean)
            clean = clean.strip()

            lines = [line.strip() for line in clean.split('\n') if line.strip()]
            # Filter out non-Thai/non-lyrics lines
            thai_lines = [
                l for l in lines
                if _is_thai_text(l) and len(l) > 3
            ]
            if len(thai_lines) > 5:
                return thai_lines

    # Strategy 2: Fallback — look for dense Thai text blocks
    # Extract all text and find the longest block of Thai text
    extractor = _TextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass

    # Find consecutive Thai text lines
    current_block: list[str] = []
    best_block: list[str] = []

    for text in extractor.texts:
        if _is_thai_text(text) and len(text) > 3 and len(text) < 200:
            current_block.append(text)
        else:
            if len(current_block) > len(best_block):
                best_block = current_block[:]
            current_block = []

    if len(current_block) > len(best_block):
        best_block = current_block

    if len(best_block) > 5:
        return best_block

    return []


def _is_thai_text(text: str) -> bool:
    """Check if text contains Thai characters."""
    thai_chars = sum(1 for c in text if '\u0e00' <= c <= '\u0e7f')
    return thai_chars > len(text) * 0.3


def _extract_key_phrases(whisper_texts: list[str], max_phrases: int = 3) -> list[str]:
    """Extract key phrases from Whisper output for searching."""
    # Take the longest/most confident segments
    sorted_texts = sorted(whisper_texts, key=len, reverse=True)
    phrases = []
    for text in sorted_texts[:max_phrases * 2]:
        clean = text.strip()
        if _is_thai_text(clean) and len(clean) > 5:
            # Take first 30 chars max for search
            phrases.append(clean[:30])
            if len(phrases) >= max_phrases:
                break
    return phrases


def search_lyrics(
    whisper_texts: list[str],
    song_name: str | None = None,
) -> dict | None:
    """
    Search for Thai song lyrics on the web.

    Args:
        whisper_texts: Rough transcription from Whisper
        song_name: Song name if known (from Gemini identification)

    Returns dict with:
        - source: str (URL where lyrics were found)
        - lyrics: list[str] (correct lyrics lines)
        - song: str | None (identified song name)
    
    Returns None if search fails.
    """
    if not whisper_texts:
        return None

    # Build search queries
    queries = []

    if song_name:
        queries.append(f"เนื้อเพลง {song_name}")
        queries.append(f"{song_name} lyrics เนื้อเพลง")

    # Extract key phrases from Whisper output
    key_phrases = _extract_key_phrases(whisper_texts)
    for phrase in key_phrases:
        queries.append(f"เนื้อเพลง {phrase}")

    logger.info(f"Searching lyrics with {len(queries)} queries")

    for query in queries:
        logger.info(f"  Searching: '{query}'")
        results = _search_duckduckgo(query)

        if not results:
            logger.info("  No search results")
            continue

        # Try each result
        for result in results[:5]:
            url = result["url"]
            title = result["title"]

            # Prefer known lyrics sites
            is_lyrics_site = any(site in url for site in _LYRICS_SITES)

            # Skip non-relevant results
            if not is_lyrics_site and "เนื้อเพลง" not in title and "lyric" not in title.lower():
                continue

            logger.info(f"  Trying: {title} ({url})")

            html = _fetch_url(url)
            if not html:
                continue

            lyrics = _extract_lyrics_from_html(html)
            if lyrics and len(lyrics) >= 5:
                # Extract song name from page title
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
                page_title = title_match.group(1) if title_match else title

                # Clean up song name from title
                found_song = page_title
                for remove in ["เนื้อเพลง", "lyrics", "Lyrics", "| Sanook", "- SiamZone", "| Kapook"]:
                    found_song = found_song.replace(remove, "")
                found_song = found_song.strip(" -|")

                logger.info(f"  ✅ Found {len(lyrics)} lyrics lines from {url}")
                return {
                    "source": url,
                    "lyrics": lyrics,
                    "song": found_song if found_song else None,
                }

    logger.info("No lyrics found from web search")
    return None


def search_lyrics_with_gemini(
    whisper_texts: list[str],
) -> dict | None:
    """
    Fallback: Use Gemini text-only to identify song and recall lyrics.
    Much cheaper than audio processing.
    """
    try:
        from gemini_correction import _call_gemini, GEMINI_API_KEY
        if not GEMINI_API_KEY:
            return None

        # Take a sample of Whisper text
        sample = " ".join(whisper_texts[:10])

        prompt = f"""จากเนื้อเพลงคร่าวๆ ที่ AI ถอดมา (อาจมีคำผิดมาก):
{sample}

1. ระบุชื่อเพลงไทยนี้ให้ได้
2. ถ้าจำได้ ให้เขียนเนื้อเพลงที่ถูกต้องทั้งหมด (ทุกท่อน)
3. ตอบเป็น JSON:
{{"song": "ชื่อเพลง", "artist": "ศิลปิน", "lyrics": ["บรรทัด1", "บรรทัด2", ...]}}
4. ถ้าจำไม่ได้ ให้ตอบ {{"song": null, "artist": null, "lyrics": []}}"""

        result = _call_gemini(prompt)
        if not result:
            return None

        candidates = result.get("candidates", [])
        if not candidates:
            return None

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                return None

        song = data.get("song")
        lyrics = data.get("lyrics", [])
        artist = data.get("artist")

        if not lyrics or not isinstance(lyrics, list):
            return None

        lyrics = [l.strip() for l in lyrics if isinstance(l, str) and l.strip()]
        if len(lyrics) < 3:
            return None

        logger.info(f"Gemini text identified: '{song}' by '{artist}' ({len(lyrics)} lines)")
        return {
            "source": "gemini-text",
            "lyrics": lyrics,
            "song": f"{song} — {artist}" if artist else song,
        }

    except Exception as e:
        logger.warning(f"Gemini lyrics search failed: {e}")
        return None
