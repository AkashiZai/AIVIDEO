"""
FFmpeg Service — Burns captions into video using FFmpeg drawtext filters.
"""
from __future__ import annotations
import os, subprocess, json
from typing import Optional, Callable
from models import TranscriptionSegment, CaptionConfig
from caption_styles import build_caption_filters

def get_video_info(video_path: str) -> dict:
    try:
        result = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", video_path], capture_output=True, text=True, timeout=30)
        return json.loads(result.stdout)
    except: return {}

def get_video_dimensions(video_path: str) -> tuple[int, int]:
    for s in get_video_info(video_path).get("streams", []):
        if s.get("codec_type") == "video": return (int(s.get("width", 1920)), int(s.get("height", 1080)))
    return (1920, 1080)

def get_video_duration(video_path: str) -> float:
    d = get_video_info(video_path).get("format", {}).get("duration")
    return float(d) if d else 0.0

def burn_captions(input_path: str, output_path: str, segments: list[TranscriptionSegment], config: CaptionConfig, on_progress: Optional[Callable[[int, str], None]] = None) -> str:
    if on_progress: on_progress(5, "Preparing filters...")
    width, _ = get_video_dimensions(input_path)
    duration = get_video_duration(input_path)
    filters = build_caption_filters(segments, config, width)

    if not filters:
        cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path]
    else:
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", ",".join(filters), "-c:a", "copy", "-c:v", "libx264", "-preset", "fast", "-crf", "23", output_path]

    if on_progress: on_progress(10, "Burning captions...")

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        stderr_output = ""
        if process.stderr:
            for line in process.stderr:
                stderr_output += line
                if "time=" in line and duration > 0 and on_progress:
                    try:
                        parts = line.split("time=")[1].split(" ")[0].split(":")
                        if len(parts) == 3:
                            ct = float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
                            on_progress(min(95, int((ct/duration)*85)+10), f"Rendering... {min(95, int((ct/duration)*85)+10)}%")
                    except: pass
        process.wait()
        if process.returncode != 0: raise RuntimeError(f"FFmpeg failed:\n{stderr_output[-500:]}")
    except FileNotFoundError:
        raise RuntimeError("FFmpeg not found. Install FFmpeg and ensure it's in PATH.")

    if on_progress: on_progress(100, "Export complete")
    return output_path
