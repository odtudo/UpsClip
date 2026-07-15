import hashlib
import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from ...config import Settings
from .profiles import AnalysisProfile


@dataclass(frozen=True)
class SourceIdentity:
    platform: str
    vod_id: str


def parse_source_identity(url: str) -> SourceIdentity:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"twitch.tv", "www.twitch.tv", "m.twitch.tv"}:
        match = re.fullmatch(r"/videos/(\d+)/?", parsed.path)
        if not match:
            raise ValueError("Twitch URL must identify one VOD")
        return SourceIdentity("twitch", match.group(1))
    if host == "youtu.be":
        vod_id = parsed.path.strip("/")
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        vod_id = parse_qs(parsed.query).get("v", [""])[0]
        if not vod_id and parsed.path.startswith(("/live/", "/shorts/")):
            vod_id = parsed.path.strip("/").split("/")[-1]
    else:
        raise ValueError("Unsupported VOD platform")
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", vod_id):
        raise ValueError("YouTube URL must identify one video")
    return SourceIdentity("youtube", vod_id)


def build_cache_key(identity: SourceIdentity, profile: AnalysisProfile, settings: Settings) -> str:
    relevant = {
        "platform": identity.platform,
        "vod_id": identity.vod_id,
        # Phase 3 tuning has its own derivative fingerprint and must not invalidate media sampling.
        "profile": profile.model_dump(exclude={"phase_detection"}),
        "pipeline_version": settings.vod_analysis_pipeline_version,
        "transcription_model": settings.whisper_model,
        "probe_model": settings.vod_analysis_probe_model,
        "window_seconds": settings.vod_analysis_window_seconds,
        "audio_sample_seconds": settings.vod_analysis_audio_sample_seconds,
        "visual_samples_per_window": settings.vod_analysis_visual_samples_per_window,
        "fetch_block_seconds": settings.vod_analysis_fetch_block_seconds,
        "max_seconds": settings.vod_analysis_max_seconds,
        "vad_version": "faster-whisper-silero-v1",
        "visual_analyzer": "opencv-yunet-coarse-v1",
        "semantic_analyzer": "fixture-v1" if settings.vod_analysis_fixture_mode else "phase2-signals-only",
        "minimum_candidate_score": settings.vod_analysis_minimum_candidate_score,
    }
    encoded = json.dumps(relevant, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
