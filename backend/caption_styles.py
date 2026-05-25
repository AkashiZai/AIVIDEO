"""
Caption Styles — FFmpeg drawtext filter builders for 4 caption styles.

Each style function returns a list of FFmpeg filter strings that can be
chained together in a single filtergraph.
"""

from __future__ import annotations

from models import (
    CaptionConfig,
    CaptionStyleType,
    FontSize,
    CaptionPosition,
    TranscriptionSegment,
    WordTimestamp,
)


# ---------------------------------------------------------------------------
# Font size mapping
# ---------------------------------------------------------------------------

FONT_SIZES = {
    FontSize.SMALL: 28,
    FontSize.MEDIUM: 42,
    FontSize.LARGE: 60,
}

# ---------------------------------------------------------------------------
# Position mapping (returns FFmpeg y expression)
# ---------------------------------------------------------------------------

def _get_y_position(position: CaptionPosition, font_size: int) -> str:
    """Returns FFmpeg y-coordinate expression for caption position."""
    margin = 40
    if position == CaptionPosition.TOP:
        return str(margin)
    elif position == CaptionPosition.CENTER:
        return f"(h-{font_size})/2"
    else:  # BOTTOM
        return f"h-{font_size}-{margin}"


def _hex_to_ffmpeg_color(hex_color: str) -> str:
    """Converts #RRGGBB to FFmpeg 0xRRGGBB format."""
    c = hex_color.lstrip("#")
    return f"0x{c}"


def _escape_text(text: str) -> str:
    """Escapes special characters for FFmpeg drawtext."""
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "'\\''")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    return text


# ---------------------------------------------------------------------------
# Style: TikTok
# ---------------------------------------------------------------------------

def build_tiktok_filters(
    segments: list[TranscriptionSegment],
    config: CaptionConfig,
    video_width: int = 1920,
) -> list[str]:
    """
    TikTok style: One word at a time, large bold text, center position,
    white text with black stroke.
    """
    font_size = FONT_SIZES[config.font_size]
    color = _hex_to_ffmpeg_color(config.text_color)
    y_pos = _get_y_position(config.position, font_size)
    filters: list[str] = []

    for seg in segments:
        for word in seg.words:
            if not word.word.strip():
                continue
            text = _escape_text(word.word.strip())
            start = word.start
            end = word.end

            # Main text with border (stroke effect)
            f = (
                f"drawtext=text='{text}'"
                f":fontsize={font_size}"
                f":fontcolor={color}"
                f":borderw=4"
                f":bordercolor=0x000000"
                f":x=(w-text_w)/2"
                f":y={y_pos}"
                f":enable='between(t,{start:.3f},{end:.3f})'"
                f":font='Impact'"
            )
            filters.append(f)

    return filters


# ---------------------------------------------------------------------------
# Style: Subtitle
# ---------------------------------------------------------------------------

def build_subtitle_filters(
    segments: list[TranscriptionSegment],
    config: CaptionConfig,
    video_width: int = 1920,
) -> list[str]:
    """
    Classic subtitle: 1-2 lines at a time, semi-transparent background bar,
    bottom of screen.
    """
    font_size = FONT_SIZES[config.font_size]
    color = _hex_to_ffmpeg_color(config.text_color)
    y_pos = _get_y_position(config.position, font_size)
    filters: list[str] = []

    for seg in segments:
        text = _escape_text(seg.text.strip())
        if not text:
            continue
        start = seg.start
        end = seg.end
        pad = 12

        # Semi-transparent background box
        box_y = y_pos
        bg = (
            f"drawbox="
            f"x=0"
            f":y={box_y}-{pad}"
            f":w=iw"
            f":h={font_size}+{pad * 2}"
            f":color=0x000000@0.6"
            f":t=fill"
            f":enable='between(t,{start:.3f},{end:.3f})'"
        )
        filters.append(bg)

        # Text
        f = (
            f"drawtext=text='{text}'"
            f":fontsize={font_size}"
            f":fontcolor={color}"
            f":x=(w-text_w)/2"
            f":y={y_pos}"
            f":enable='between(t,{start:.3f},{end:.3f})'"
            f":font='Arial'"
        )
        filters.append(f)

    return filters


# ---------------------------------------------------------------------------
# Style: Word-by-Word
# ---------------------------------------------------------------------------

def build_word_by_word_filters(
    segments: list[TranscriptionSegment],
    config: CaptionConfig,
    video_width: int = 1920,
) -> list[str]:
    """
    Word-by-word: Each word appears and stays, building up a sentence,
    then clears when the segment ends. Left-aligned, mid-screen.
    """
    font_size = FONT_SIZES[config.font_size]
    color = _hex_to_ffmpeg_color(config.text_color)
    y_pos = _get_y_position(config.position, font_size)
    filters: list[str] = []
    margin_x = 60

    for seg in segments:
        if not seg.words:
            continue

        seg_end = seg.end

        # Build cumulative text for each word
        cumulative_text = ""
        for i, word in enumerate(seg.words):
            cumulative_text += word.word.strip()
            if i < len(seg.words) - 1:
                cumulative_text += " "

            text = _escape_text(cumulative_text)
            start = word.start
            # End when next word starts, or segment ends
            end = seg.words[i + 1].start if i < len(seg.words) - 1 else seg_end

            # Background
            bg = (
                f"drawbox="
                f"x={margin_x - 10}"
                f":y={y_pos}-8"
                f":w=iw-{margin_x * 2 - 20}"
                f":h={font_size}+16"
                f":color=0x000000@0.5"
                f":t=fill"
                f":enable='between(t,{start:.3f},{end:.3f})'"
            )
            filters.append(bg)

            f = (
                f"drawtext=text='{text}'"
                f":fontsize={font_size}"
                f":fontcolor={color}"
                f":x={margin_x}"
                f":y={y_pos}"
                f":enable='between(t,{start:.3f},{end:.3f})'"
                f":font='Arial'"
            )
            filters.append(f)

    return filters


# ---------------------------------------------------------------------------
# Style: Karaoke
# ---------------------------------------------------------------------------

def build_karaoke_filters(
    segments: list[TranscriptionSegment],
    config: CaptionConfig,
    video_width: int = 1920,
) -> list[str]:
    """
    Karaoke: Full line visible, active word highlighted in yellow,
    sweeps left to right per word timing.
    """
    font_size = FONT_SIZES[config.font_size]
    color = _hex_to_ffmpeg_color(config.text_color)
    highlight = "0xFFFF00"  # Yellow highlight
    y_pos = _get_y_position(config.position, font_size)
    filters: list[str] = []

    for seg in segments:
        if not seg.words:
            continue

        full_text = _escape_text(seg.text.strip())
        seg_start = seg.start
        seg_end = seg.end

        # Base layer: full line in normal color (dimmed)
        base = (
            f"drawtext=text='{full_text}'"
            f":fontsize={font_size}"
            f":fontcolor={color}@0.4"
            f":x=(w-text_w)/2"
            f":y={y_pos}"
            f":enable='between(t,{seg_start:.3f},{seg_end:.3f})'"
            f":font='Arial'"
        )
        filters.append(base)

        # Highlight layer: per-word, one at a time in yellow
        for word in seg.words:
            word_text = _escape_text(word.word.strip())
            if not word_text:
                continue

            highlight_filter = (
                f"drawtext=text='{word_text}'"
                f":fontsize={font_size}"
                f":fontcolor={highlight}"
                f":borderw=2"
                f":bordercolor=0x000000"
                f":x=(w-text_w)/2"
                f":y={y_pos}+{font_size}+10"
                f":enable='between(t,{word.start:.3f},{word.end:.3f})'"
                f":font='Arial'"
            )
            filters.append(highlight_filter)

    return filters


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def build_caption_filters(
    segments: list[TranscriptionSegment],
    config: CaptionConfig,
    video_width: int = 1920,
) -> list[str]:
    """
    Dispatches to the appropriate style builder based on config.style.

    Returns a list of FFmpeg drawtext/drawbox filter strings.
    """
    builders = {
        CaptionStyleType.TIKTOK: build_tiktok_filters,
        CaptionStyleType.SUBTITLE: build_subtitle_filters,
        CaptionStyleType.WORD_BY_WORD: build_word_by_word_filters,
        CaptionStyleType.KARAOKE: build_karaoke_filters,
    }

    builder = builders.get(config.style, build_subtitle_filters)
    return builder(segments, config, video_width)
