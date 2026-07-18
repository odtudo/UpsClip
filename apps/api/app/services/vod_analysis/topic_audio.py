from __future__ import annotations

from pathlib import Path

from ...config import Settings
from ..process import run_command
from .metadata import StreamAccess


def extract_analysis_audio(
    access: StreamAccess,
    duration: float,
    destination: Path,
    settings: Settings,
) -> Path:
    """Download only the selected audio representation and decode a bounded prefix."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    input_options: list[str] = []
    if access.user_agent:
        input_options.extend(["-user_agent", access.user_agent])
    if access.referer:
        input_options.extend(["-referer", access.referer])
    run_command(
        [
            settings.ffmpeg_path,
            "-y",
            *input_options,
            "-i",
            access.audio_url,
            "-t",
            f"{duration:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        label="VOD topic audio extraction",
        timeout=settings.vod_topic_audio_timeout_seconds,
    )
    if not destination.is_file() or destination.stat().st_size <= 44:
        raise RuntimeError("Audio extraction failed: FFmpeg produced no PCM audio")
    return destination


def chunk_ranges(duration: float, chunk_seconds: int, overlap_seconds: int) -> list[tuple[float, float]]:
    if duration <= 0 or chunk_seconds <= 0 or overlap_seconds < 0 or overlap_seconds >= chunk_seconds:
        raise ValueError("Invalid transcription chunk configuration")
    result: list[tuple[float, float]] = []
    start = 0.0
    while start < duration:
        end = min(duration, start + chunk_seconds)
        result.append((start, end))
        if end >= duration:
            break
        start = end - overlap_seconds
    return result


def extract_audio_chunk(
    source: Path, start: float, end: float, destination: Path, settings: Settings
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            settings.ffmpeg_path,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(source),
            "-t",
            f"{end - start:.3f}",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        label="Whisper chunk extraction",
        timeout=180,
    )
    return destination
