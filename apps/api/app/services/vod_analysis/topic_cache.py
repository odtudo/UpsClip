from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from ...config import Settings
from .cache import SourceIdentity


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def topic_cache_keys(
    identity: SourceIdentity,
    profile_id: str,
    settings: Settings,
    *,
    source_url: str = "",
    transcript_hash: str = "pending",
) -> dict[str, str]:
    source = {
        "platform": identity.platform,
        "vod_id": identity.vod_id,
        "profile": profile_id,
        "range_seconds": settings.vod_topic_analysis_max_seconds,
        "fixture_mode": settings.vod_analysis_fixture_mode,
        "source_fingerprint": _fingerprint(
            {"platform": identity.platform, "vod_id": identity.vod_id, "url": source_url}
        ),
    }
    audio = _fingerprint({**source, "audio": "pcm-s16le-mono-16000-v1"})
    transcription = _fingerprint(
        {
            "audio_key": audio,
            "model": settings.whisper_analysis_model,
            "language": "es",
            "chunk_seconds": settings.transcription_chunk_seconds,
            "overlap_seconds": settings.transcription_overlap_seconds,
            "word_timestamps": True,
            "vad_filter": True,
            "version": "whisper-chunks-v1",
        }
    )
    segmentation = _fingerprint(
        {
            "transcription_key": transcription,
            "transcript_hash": transcript_hash,
            "cleaning": "transcript-clean-v1",
            "embedding_model": settings.semantic_embedding_model,
            "semantic_windows": [
                settings.semantic_window_min_seconds,
                settings.semantic_window_target_seconds,
                settings.semantic_window_max_seconds,
            ],
            "topic_durations": [settings.topic_min_seconds, settings.topic_max_seconds],
            "keyword_extraction": "spanish-tfidf-ngram-v2",
            "topic_labeling": "grounded-topic-label-v2",
            "representative_sentences": "distributed-deduplicated-v2",
            "version": "topic-segmentation-v4",
        }
    )
    candidates = _fingerprint(
        {
            "segmentation_key": segmentation,
            "title_generation": "grounded-title-v7",
            "scoring": "editorial-scoring-v7",
            "quality_gate": "candidate-quality-gate-v7",
            "minimum_score": settings.vod_analysis_minimum_candidate_score,
            "durations": [
                settings.candidate_min_seconds,
                settings.candidate_target_min_seconds,
                settings.candidate_target_max_seconds,
                settings.candidate_max_seconds,
            ],
            "max_candidates": settings.vod_topic_max_candidates,
            "pipeline": settings.vod_topic_analysis_pipeline_version,
        }
    )
    return {
        "audio": audio,
        "transcription": transcription,
        "segmentation": segmentation,
        "candidates": candidates,
    }


def cache_directory(settings: Settings, stage: str, key: str) -> Path:
    return settings.data_dir / "analysis" / "topic_cache" / stage / key


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def copy_artifact(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
