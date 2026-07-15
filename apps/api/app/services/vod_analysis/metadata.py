import json
from dataclasses import dataclass
from typing import Any

from ...config import Settings
from ..media import _friendly_twitch_error, _twitch_args
from ..process import ProcessError, run_command
from .cache import SourceIdentity
from .schemas import CoarseVodMetadata


@dataclass(frozen=True)
class StreamAccess:
    audio_url: str
    video_url: str | None
    audio_kbps: float
    video_kbps: float
    user_agent: str | None = None
    referer: str | None = None


def _run_ytdlp_json(source_url: str, settings: Settings) -> dict[str, Any]:
    cookie_args = _twitch_args(settings) if "twitch.tv/" in source_url.lower() else []
    try:
        result = run_command(
            [
                settings.ytdlp_path,
                *cookie_args,
                "--dump-single-json",
                "--skip-download",
                "--no-playlist",
                source_url,
            ],
            label="VOD analysis metadata",
            timeout=120,
        )
    except ProcessError as exc:
        if "twitch" in source_url.lower():
            raise _friendly_twitch_error(exc) from exc
        raise RuntimeError(f"VOD metadata unavailable: {exc}") from exc
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("VOD metadata unavailable: yt-dlp returned invalid JSON") from exc


def _format_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "format_id": item.get("format_id"),
        "ext": item.get("ext"),
        "protocol": item.get("protocol"),
        "acodec": item.get("acodec"),
        "vcodec": item.get("vcodec"),
        "abr": item.get("abr"),
        "vbr": item.get("vbr"),
        "tbr": item.get("tbr"),
        "width": item.get("width"),
        "height": item.get("height"),
        "fps": item.get("fps"),
    }


def inspect_analysis_metadata(
    source_url: str, identity: SourceIdentity, settings: Settings
) -> tuple[CoarseVodMetadata, dict[str, Any]]:
    raw = _run_ytdlp_json(source_url, settings)
    duration = raw.get("duration")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise RuntimeError("VOD metadata unavailable: duration is missing or invalid")
    formats = [item for item in raw.get("formats", []) if isinstance(item, dict)]
    audio = [_format_summary(item) for item in formats if item.get("acodec") not in {None, "none"}]
    video = [_format_summary(item) for item in formats if item.get("vcodec") not in {None, "none"}]
    if not audio:
        raise RuntimeError("No audio stream is available for coarse VOD analysis")
    metadata = CoarseVodMetadata(
        platform=identity.platform,
        extractor=str(raw.get("extractor") or raw.get("extractor_key") or identity.platform),
        vod_id=str(raw.get("id") or identity.vod_id),
        title=str(raw.get("title") or "Untitled VOD"),
        uploader=raw.get("uploader"),
        channel=raw.get("channel"),
        duration_seconds=float(duration),
        chapters=raw.get("chapters") or [],
        original_url=str(raw.get("webpage_url") or raw.get("original_url") or source_url),
        availability=raw.get("availability"),
        audio_formats=audio,
        video_formats=video,
    )
    return metadata, raw


def _pick_audio(formats: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [item for item in formats if item.get("acodec") not in {None, "none"} and item.get("url")]
    if not candidates:
        raise RuntimeError("No audio stream URL is available")
    audio_only = [item for item in candidates if item.get("vcodec") == "none"]
    pool = audio_only or candidates
    return min(pool, key=lambda item: float(item.get("abr") or item.get("tbr") or 192))


def _pick_video(formats: list[dict[str, Any]], target_height: int = 360) -> dict[str, Any] | None:
    candidates = [item for item in formats if item.get("vcodec") not in {None, "none"} and item.get("url")]
    if not candidates:
        return None
    maximum = max(480, target_height)
    low = [item for item in candidates if 144 <= int(item.get("height") or 0) <= maximum]
    pool = low or candidates
    return min(
        pool,
        key=lambda item: (
            abs(int(item.get("height") or target_height) - target_height),
            float(item.get("tbr") or item.get("vbr") or 5000),
        ),
    )


def stream_access_from_metadata(raw: dict[str, Any], *, video_height: int = 360) -> StreamAccess:
    formats = [item for item in raw.get("formats", []) if isinstance(item, dict)]
    audio = _pick_audio(formats)
    video = _pick_video(formats, video_height)
    audio_kbps = float(
        audio.get("abr") or (audio.get("tbr") if audio.get("vcodec") == "none" else 128) or 128
    )
    video_kbps = float((video or {}).get("vbr") or (video or {}).get("tbr") or 800)
    headers = {
        **(raw.get("http_headers") or {}),
        **(audio.get("http_headers") or {}),
    }
    return StreamAccess(
        audio_url=str(audio["url"]),
        video_url=str(video["url"]) if video else None,
        audio_kbps=max(16.0, audio_kbps),
        video_kbps=max(100.0, video_kbps),
        user_agent=headers.get("User-Agent"),
        referer=headers.get("Referer"),
    )
