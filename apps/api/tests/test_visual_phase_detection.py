import numpy as np

from apps.api.app.services.smart_vertical.types import FaceDetection, Rect
from apps.api.app.services.vod_analysis.layout_detection import (
    apply_hysteresis,
    build_layout_timeline,
    classify_frame,
    layout_cache_key,
    merge_layout_segments,
    phase_timeline_from_layout,
    sample_timestamps,
)
from apps.api.app.services.vod_analysis.profiles import ILLOJUAN
from apps.api.app.services.vod_analysis.schemas import LayoutFrameSample
from apps.api.app.services.vod_analysis.visual_profiles import LayoutMatch


class Detector:
    def __init__(self, detections):
        self.detections = detections

    def detect(self, frame, timestamp):
        return self.detections


def detection(x: int, y: int, width: int, height: int, confidence: float = 0.9) -> FaceDetection:
    return FaceDetection(0, Rect(x, y, width, height), confidence, 1920, 1080)


class Matcher:
    def __init__(self, matched):
        self.matched = matched

    def match(self, frame, detections):
        return self.matched


def classify(layout_id, phase, test_settings, detections=()):
    frame = np.full((1080, 1920, 3), 120, dtype=np.uint8)
    match = LayoutMatch(
        layout_id=layout_id,
        phase=phase,
        match_score=0.8,
        second_best_score=0.2,
        score_margin=0.6,
        face_area_ratio=0.04,
    )
    return classify_frame(frame, 10, 5, Detector(list(detections)), Matcher(match), test_settings)[0]


def test_no_face_maps_to_waiting(test_settings) -> None:
    sample = classify("waiting_unmatched", "waiting_or_music", test_settings)
    assert (sample.layout, sample.phase) == ("no_face", "waiting_or_music")
    assert sample.layout_id == "waiting_unmatched"


def test_fullscreen_face_maps_to_talking(test_settings) -> None:
    sample = classify("full_camera_room", "talking", test_settings)
    assert (sample.layout, sample.phase) == ("fullscreen_face", "talking")
    assert sample.layout_id == "full_camera_room"


def test_small_edge_facecam_maps_to_gameplay(test_settings) -> None:
    sample = classify("gameplay_left", "gameplay", test_settings)
    assert (sample.layout, sample.phase) == ("small_facecam", "gameplay")
    assert sample.layout_id == "gameplay_left"


def test_ambiguous_face_maps_to_unknown(test_settings) -> None:
    sample = classify("unknown", "unknown", test_settings)
    assert (sample.layout, sample.phase) == ("unknown", "unknown")
    assert sample.layout_id == "unknown"


def sample(index: int, layout: str) -> LayoutFrameSample:
    phase = {
        "no_face": "waiting_or_music",
        "fullscreen_face": "talking",
        "small_facecam": "gameplay",
        "unknown": "unknown",
    }[layout]
    layout_id = {
        "no_face": "waiting_unmatched",
        "fullscreen_face": "full_camera_room",
        "small_facecam": "gameplay_left",
        "unknown": "unknown",
    }[layout]
    return LayoutFrameSample(
        index=index,
        frame_timestamp=index * 2,
        layout=layout,
        layout_id=layout_id,
        phase=phase,
        confidence=0.8,
        face_area_ratio=0.1 if layout == "fullscreen_face" else 0.02,
    )


def test_hysteresis_requires_three_consecutive_samples() -> None:
    values = [
        sample(index, layout)
        for index, layout in enumerate(
            [
                "fullscreen_face",
                "fullscreen_face",
                "small_facecam",
                "fullscreen_face",
                "small_facecam",
                "small_facecam",
                "small_facecam",
            ]
        )
    ]
    smoothed = apply_hysteresis(values, 3)
    assert [item.layout for item in smoothed] == [
        "fullscreen_face",
        "fullscreen_face",
        "fullscreen_face",
        "fullscreen_face",
        "small_facecam",
        "small_facecam",
        "small_facecam",
    ]


def test_unknown_single_frame_does_not_change_state() -> None:
    values = [
        sample(index, layout)
        for index, layout in enumerate(
            [
                "no_face",
                "no_face",
                "unknown",
                "no_face",
                "no_face",
            ]
        )
    ]
    assert {item.layout for item in apply_hysteresis(values, 3)} == {"no_face"}


def test_layout_timeline_and_phase_transitions(test_settings) -> None:
    settings = test_settings.model_copy(
        update={
            "layout_sample_seconds": 2,
            "layout_transition_confirmation": 3,
        }
    )
    raw = [
        sample(index, layout)
        for index, layout in enumerate(["no_face"] * 4 + ["fullscreen_face"] * 5 + ["small_facecam"] * 4)
    ]
    timeline = build_layout_timeline(raw, 26, "layout-key", "coarse-key", settings)
    assert [(item.layout, item.start, item.end) for item in timeline.segments] == [
        ("no_face", 0, 8),
        ("fullscreen_face", 8, 18),
        ("small_facecam", 18, 26),
    ]
    phases = phase_timeline_from_layout(timeline, ILLOJUAN)
    assert [item.phase for item in phases.segments] == [
        "waiting_or_music",
        "talking",
        "gameplay",
    ]


def test_sampling_interval_is_configurable() -> None:
    assert sample_timestamps(7, 2) == [0, 2, 4, 6]
    assert sample_timestamps(7, 3) == [0, 3, 6]


def test_layout_cache_depends_on_visual_configuration_only(test_settings) -> None:
    baseline = layout_cache_key("twitch", "123", "illojuan", test_settings)
    audio_changed = test_settings.model_copy(update={"vod_analysis_probe_model": "small"})
    interval_changed = test_settings.model_copy(update={"layout_sample_seconds": 3})
    confirmation_changed = test_settings.model_copy(update={"layout_transition_confirmation": 4})
    assert layout_cache_key("twitch", "123", "illojuan", audio_changed) == baseline
    assert layout_cache_key("twitch", "123", "illojuan", interval_changed) != baseline
    assert layout_cache_key("twitch", "123", "illojuan", confirmation_changed) != baseline


def test_merge_keeps_ambiguous_state_visible() -> None:
    segments = merge_layout_segments([sample(0, "no_face"), sample(1, "unknown"), sample(2, "unknown")], 6, 2)
    assert [item.layout for item in segments] == ["no_face", "unknown"]
