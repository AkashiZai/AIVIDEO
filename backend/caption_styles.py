"""
Caption Styles — FFmpeg drawtext filter builders for 4 caption styles.
"""
from __future__ import annotations
from models import CaptionConfig, CaptionStyleType, FontSize, CaptionPosition, TranscriptionSegment

FONT_SIZES = {FontSize.SMALL: 28, FontSize.MEDIUM: 42, FontSize.LARGE: 60}

def _get_y_position(position: CaptionPosition, font_size: int) -> str:
    margin = 40
    if position == CaptionPosition.TOP: return str(margin)
    elif position == CaptionPosition.CENTER: return f"(h-{font_size})/2"
    else: return f"h-{font_size}-{margin}"

def _hex_to_ffmpeg_color(hex_color: str) -> str:
    return f"0x{hex_color.lstrip('#')}"

def _escape_text(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "'\\''")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    return text

def build_tiktok_filters(segments: list[TranscriptionSegment], config: CaptionConfig, video_width: int = 1920) -> list[str]:
    fs = FONT_SIZES[config.font_size]; color = _hex_to_ffmpeg_color(config.text_color); y = _get_y_position(config.position, fs)
    filters = []
    for seg in segments:
        for w in seg.words:
            t = _escape_text(w.word.strip())
            if not t: continue
            filters.append(f"drawtext=text='{t}':fontsize={fs}:fontcolor={color}:borderw=4:bordercolor=0x000000:x=(w-text_w)/2:y={y}:enable='between(t,{w.start:.3f},{w.end:.3f})':font='Impact'")
    return filters

def build_subtitle_filters(segments: list[TranscriptionSegment], config: CaptionConfig, video_width: int = 1920) -> list[str]:
    fs = FONT_SIZES[config.font_size]; color = _hex_to_ffmpeg_color(config.text_color); y = _get_y_position(config.position, fs)
    filters = []
    for seg in segments:
        t = _escape_text(seg.text.strip())
        if not t: continue
        pad = 12
        filters.append(f"drawbox=x=0:y={y}-{pad}:w=iw:h={fs}+{pad*2}:color=0x000000@0.6:t=fill:enable='between(t,{seg.start:.3f},{seg.end:.3f})'")
        filters.append(f"drawtext=text='{t}':fontsize={fs}:fontcolor={color}:x=(w-text_w)/2:y={y}:enable='between(t,{seg.start:.3f},{seg.end:.3f})':font='Arial'")
    return filters

def build_word_by_word_filters(segments: list[TranscriptionSegment], config: CaptionConfig, video_width: int = 1920) -> list[str]:
    fs = FONT_SIZES[config.font_size]; color = _hex_to_ffmpeg_color(config.text_color); y = _get_y_position(config.position, fs)
    filters = []; mx = 60
    for seg in segments:
        if not seg.words: continue
        cumulative = ""
        for i, w in enumerate(seg.words):
            cumulative += w.word.strip() + (" " if i < len(seg.words)-1 else "")
            t = _escape_text(cumulative); start = w.start; end = seg.words[i+1].start if i < len(seg.words)-1 else seg.end
            filters.append(f"drawbox=x={mx-10}:y={y}-8:w=iw-{mx*2-20}:h={fs}+16:color=0x000000@0.5:t=fill:enable='between(t,{start:.3f},{end:.3f})'")
            filters.append(f"drawtext=text='{t}':fontsize={fs}:fontcolor={color}:x={mx}:y={y}:enable='between(t,{start:.3f},{end:.3f})':font='Arial'")
    return filters

def build_karaoke_filters(segments: list[TranscriptionSegment], config: CaptionConfig, video_width: int = 1920) -> list[str]:
    fs = FONT_SIZES[config.font_size]; color = _hex_to_ffmpeg_color(config.text_color); y = _get_y_position(config.position, fs)
    filters = []
    for seg in segments:
        if not seg.words: continue
        full = _escape_text(seg.text.strip())
        filters.append(f"drawtext=text='{full}':fontsize={fs}:fontcolor={color}@0.4:x=(w-text_w)/2:y={y}:enable='between(t,{seg.start:.3f},{seg.end:.3f})':font='Arial'")
        for w in seg.words:
            wt = _escape_text(w.word.strip())
            if not wt: continue
            filters.append(f"drawtext=text='{wt}':fontsize={fs}:fontcolor=0xFFFF00:borderw=2:bordercolor=0x000000:x=(w-text_w)/2:y={y}+{fs}+10:enable='between(t,{w.start:.3f},{w.end:.3f})':font='Arial'")
    return filters

def build_caption_filters(segments: list[TranscriptionSegment], config: CaptionConfig, video_width: int = 1920) -> list[str]:
    builders = {CaptionStyleType.TIKTOK: build_tiktok_filters, CaptionStyleType.SUBTITLE: build_subtitle_filters, CaptionStyleType.WORD_BY_WORD: build_word_by_word_filters, CaptionStyleType.KARAOKE: build_karaoke_filters}
    return builders.get(config.style, build_subtitle_filters)(segments, config, video_width)
