from apps.api.app.services.smart_vertical.classifier import classify_scene
from apps.api.app.services.smart_vertical.face_detection import remap_detection_rect
from apps.api.app.services.smart_vertical.planner import stabilize_layouts
from apps.api.app.services.smart_vertical.types import (
    CompositionSegment,
    FaceDetection,
    Rect,
    SceneSegment,
)


def face(x: int, y: int, size: int, timestamp: float = 0) -> FaceDetection:
    return FaceDetection(timestamp, Rect(x, y, size, size), 0.9, 1920, 1080)


def test_classifies_large_central_face(test_settings) -> None:
    frames = [[face(700, 220, 580, index)] for index in range(5)]
    result = classify_scene(SceneSegment(0, 5), frames, 1920, 1080, test_settings)
    assert result.layout == "fullscreen_face"
    assert result.output_crop is None


def test_classifies_stable_corner_facecam(test_settings) -> None:
    frames = [[face(40, 35, 130, index)] for index in range(6)]
    result = classify_scene(SceneSegment(0, 5), frames, 1920, 1080, test_settings)
    assert result.layout == "small_facecam"
    assert result.facecam_position == "top_left"


def test_no_face_and_ambiguous(test_settings) -> None:
    assert classify_scene(SceneSegment(0, 3), [[], [], []], 1920, 1080, test_settings).layout == "no_face"
    frames = [
        [face(20 + index * 250, 20, 100, index), face(1500 - index * 180, 400, 90)] for index in range(5)
    ]
    assert classify_scene(SceneSegment(0, 5), frames, 1920, 1080, test_settings).layout == "uncertain"


def test_hysteresis_bridges_short_uncertain_segment(test_settings) -> None:
    items = [
        CompositionSegment(0, 3, "small_facecam", 0.8, "automatic"),
        CompositionSegment(3, 3.7, "uncertain", 0.3, "automatic"),
        CompositionSegment(3.7, 7, "small_facecam", 0.8, "automatic"),
    ]
    assert len(stabilize_layouts(items, test_settings)) == 1


def test_stable_left_column_face_is_facecam(test_settings) -> None:
    frames = [[face(160, 430, 110, index)] for index in range(8)]
    result = classify_scene(SceneSegment(0, 8), frames, 1920, 1080, test_settings)
    assert result.layout == "small_facecam"
    assert result.facecam_position == "left_column"
    assert result.detection_source == "automatic_side_facecam"


def test_stable_right_column_face_is_facecam(test_settings) -> None:
    frames = [[face(1650, 430, 110, index)] for index in range(8)]
    result = classify_scene(SceneSegment(0, 8), frames, 1920, 1080, test_settings)
    assert result.layout == "small_facecam"
    assert result.facecam_position == "right_column"


def test_yunet_box_is_remapped_to_source_resolution() -> None:
    assert remap_detection_rect([100, 50, 80, 120], 2 / 3) == Rect(150, 75, 120, 180)
