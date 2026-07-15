from pathlib import Path

import pytest

from apps.api.app.services.vod_analysis.cache import build_cache_key, parse_source_identity
from apps.api.app.services.vod_analysis.fixtures import phase_detection_fixture
from apps.api.app.services.vod_analysis.phase_detection import (
    build_phase_timeline,
    classify_window,
    phase_cache_key,
)
from apps.api.app.services.vod_analysis.profiles import ILLOJUAN
from apps.api.app.services.vod_analysis.schemas import CoarseTimeline, CoarseVodMetadata
from apps.api.app.services.vod_analysis.timeline import load_phase_timeline, persist_phase_timeline


def metadata(chapters=None) -> CoarseVodMetadata:
    return CoarseVodMetadata(
        platform="twitch",
        extractor="twitch:vod",
        vod_id="123",
        title="IlloJuan fixture",
        uploader="IlloJuan",
        duration_seconds=10_800,
        original_url="https://www.twitch.tv/videos/123",
        chapters=chapters or [],
    )


@pytest.mark.parametrize(
    ("phase", "expected", "reason"),
    [
        ("waiting_or_music", "waiting_or_music", "repetitive_transcript"),
        ("talking", "talking", "high_voice_ratio"),
        ("gameplay", "gameplay", "high_motion"),
        ("failed", "unknown", "insufficient_audio_and_visual_signals"),
    ],
)
def test_explainable_raw_phase_scores(phase: str, expected: str, reason: str) -> None:
    coarse = CoarseTimeline.model_validate(phase_detection_fixture([(phase, 1)]))
    result = classify_window(coarse.windows[0], metadata(), ILLOJUAN)
    assert result.raw_phase == expected
    assert reason in result.reasons
    assert 0 <= result.raw_confidence <= 1


def test_smoothing_bridges_unknown_gap_and_preserves_gameplay_transition() -> None:
    coarse = CoarseTimeline.model_validate(
        phase_detection_fixture(
            [
                ("talking", 4),
                ("failed", 1),
                ("talking", 4),
                ("gameplay", 4),
            ]
        )
    )
    result = build_phase_timeline(coarse, metadata(), ILLOJUAN, "v3-test")
    assert [item.phase for item in result.segments] == ["talking", "gameplay"]
    assert any("smoothed_short_unknown_gap" in item.smoothing_reasons for item in result.smoothed_windows)


def test_multiple_long_talking_blocks_primary_and_selection() -> None:
    coarse = CoarseTimeline.model_validate(
        phase_detection_fixture(
            [
                ("waiting_or_music", 4),
                ("talking", 22),
                ("gameplay", 6),
                ("talking", 24),
            ]
        )
    )
    result = build_phase_timeline(coarse, metadata(), ILLOJUAN, "v3-test")
    assert len(result.talking_blocks) == 2
    assert result.primary_talking_block_id == "talking-001"
    assert all(item.selected_for_deep_transcription for item in result.talking_blocks)
    assert result.talking_blocks[0].end_transition == "gameplay_transition"
    assert result.summary.talking_seconds == 1380


def test_short_talking_block_is_retained_but_not_selected() -> None:
    coarse = CoarseTimeline.model_validate(phase_detection_fixture([("talking", 8)]))
    result = build_phase_timeline(coarse, metadata(), ILLOJUAN, "v3-test")
    assert len(result.talking_blocks) == 1
    assert result.talking_blocks[0].relevance == "low_priority"
    assert result.selected_talking_blocks == []
    assert "primary_talking_block_not_found" in result.warnings


def test_chapters_are_auxiliary_reason_codes() -> None:
    coarse = CoarseTimeline.model_validate(phase_detection_fixture([("unknown", 1)]))
    result = classify_window(
        coarse.windows[0],
        metadata([{"start_time": 0, "end_time": 30, "title": "Jugando al juego"}]),
        ILLOJUAN,
    )
    assert "chapter_title_gameplay_hint" in result.reasons


def test_phase_cache_invalidation_and_serialization(tmp_path: Path) -> None:
    coarse = CoarseTimeline.model_validate(phase_detection_fixture())
    first = phase_cache_key(coarse, ILLOJUAN, "v3-a")
    assert first != phase_cache_key(coarse, ILLOJUAN, "v3-b")
    timeline = build_phase_timeline(coarse, metadata(), ILLOJUAN, "v3-a")
    path = tmp_path / "phase_timeline.json"
    persist_phase_timeline(path, timeline)
    assert load_phase_timeline(path, timeline.phase_cache_key) == timeline
    assert load_phase_timeline(path, "stale") is None


def test_phase_tuning_invalidates_only_phase_cache(test_settings) -> None:
    coarse = CoarseTimeline.model_validate(phase_detection_fixture())
    changed_detection = ILLOJUAN.phase_detection.model_copy(update={"raw_phase_min_confidence": 0.51})
    changed_profile = ILLOJUAN.model_copy(update={"phase_detection": changed_detection})
    identity = parse_source_identity("https://www.twitch.tv/videos/123")
    assert build_cache_key(identity, ILLOJUAN, test_settings) == build_cache_key(
        identity, changed_profile, test_settings
    )
    assert phase_cache_key(coarse, ILLOJUAN, "v3") != phase_cache_key(coarse, changed_profile, "v3")


def test_existing_real_silent_timeline_does_not_invent_talking_block() -> None:
    path = Path(
        "data/analysis/cache/0bc5d794dabe5fad0288a708cade8402cd21c57b3b72bf81869217e0ba27d7fe/coarse_timeline.json"
    )
    if not path.exists():
        pytest.skip("real cached Phase 2 smoke timeline is not present")
    coarse = CoarseTimeline.model_validate_json(path.read_text(encoding="utf-8"))
    result = build_phase_timeline(coarse, metadata(), ILLOJUAN, "v3-real-smoke")
    assert result.talking_blocks == []
    assert sum(item.end - item.start for item in result.segments) == 60
