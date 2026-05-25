"""
FFmpeg Service — Burns captions into video using FFmpeg drawtext filters.
"""

from __future__ import annotations

import os
import subprocess
import json
from typing import Optional, Callable

from models import (
    TranscriptionSegment,
    CaptionConfig,
)
from caption_styles import build_caption_filters


def get_video_info(video_path: str) -> dict:
    """Gets video metadata using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        info = json.loads(result.stdout)
        return info
    except Exception:
        return {}


def get_video_dimensions(video_path: str) -> tuple[int, int]:
    """Returns (width, height) of the video."""
    info = get_video_info(video_path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            w = int(stream.get("width", 1920))
            h = int(stream.get("height", 1080))
            return (w, h)
    return (1920, 1080)


def get_video_duration(video_path: str) -> float:
    """Returns the duration of the video in seconds."""
    info = get_video_info(video_path)
    fmt = info.get("format", {})
    duration = fmt.get("duration")
    if duration:
        return float(duration)
    return 0.0


def burn_captions(
    input_path: str,
    output_path: str,
    segments: list[TranscriptionSegment],
    config: CaptionConfig,
    on_progress: Optional[Callable[[int, str], None]] = None,
) -> str:
    """
    Burns captions into a video using FFmpeg drawtext filters.

    Args:
        input_path: Path to the input video file.
        output_path: Path to save the output video.
        segments: Transcription segments with word timestamps.
        config: Caption style configuration.
        on_progress: Optional callback(progress_pct, message).

    Returns:
        Path to the output video file.
    """
    if on_progress:
        on_progress(5, "Preparing filters...")

    # Get video dimensions
    width, height = get_video_dimensions(input_path)
    duration = get_video_duration(input_path)

    # Build FFmpeg filter chain
    filters = build_caption_filters(segments, config, width)

    if not filters:
        # No captions — just copy
        cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path]
    else:
        # Join all filter strings with commas
        filter_complex = ",".join(filters)

        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-vf", filter_complex,
            "-c:a", "copy",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            output_path,
        ]

    if on_progress:
        on_progress(10, "Burning captions into video...")

    # Run FFmpeg with progress parsing
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )

        # Read stderr for progress (FFmpeg outputs to stderr)
        stderr_output = ""
        if process.stderr:
            for line in process.stderr:
                stderr_output += line
                # Parse time= from FFmpeg output for progress
                if "time=" in line and duration > 0 and on_progress:
                    try:
                        time_str = line.split("time=")[1].split(" ")[0]
                        parts = time_str.split(":")
                        if len(parts) == 3:
                            current_time = (
                                float(parts[0]) * 3600
                                + float(parts[1]) * 60
                                + float(parts[2])
                            )
                            pct = min(95, int((current_time / duration) * 85) + 10)
                            on_progress(pct, f"Rendering... {pct}%")
                    except (ValueError, IndexError):
                        pass

        process.wait()

        if process.returncode != 0:
            raise RuntimeError(
                f"FFmpeg failed with code {process.returncode}:\n{stderr_output[-500:]}"
            )

    except FileNotFoundError:
        raise RuntimeError(
            "FFmpeg not found. Please install FFmpeg and ensure it's in your PATH."
        )

    if on_progress:
        on_progress(100, "Export complete")

    return output_path
