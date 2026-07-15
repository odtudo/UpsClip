from apps.api.app.services.smart_vertical.geometry import (
    aspect_crop,
    clamp_rect,
    expand_face,
    facecam_position,
    iou,
    median_rect,
    overlap_ratio,
    select_content_crop,
)
from apps.api.app.services.smart_vertical.types import Rect


def test_clamp_expansion_and_even_dimensions(test_settings) -> None:
    expanded = expand_face(Rect(0, 0, 100, 100), 1920, 1080, test_settings)
    assert expanded.x == 0 and expanded.y == 0
    assert expanded.width > 100 and expanded.height > 100
    assert expanded.width % 2 == expanded.height % 2 == 0
    assert clamp_rect(Rect(1900, 1060, 100, 100), 1920, 1080).width == 20


def test_geometry_helpers() -> None:
    left = Rect(0, 0, 400, 300)
    right = Rect(1520, 0, 400, 300)
    assert facecam_position(left, 1920, 1080) == "top_left"
    assert facecam_position(right, 1920, 1080) == "top_right"
    assert iou(left, left) == 1.0
    assert median_rect([Rect(10, 20, 100, 80), Rect(12, 22, 102, 82)]) == Rect(11, 21, 101, 81)


def test_content_crop_moves_away_from_facecam() -> None:
    facecam = Rect(0, 0, 500, 400)
    center = aspect_crop(1920, 1080, 1080 / 1186)
    crop, overlap, strategy = select_content_crop(1920, 1080, 1080 / 1186, facecam)
    assert crop.x >= center.x
    assert overlap <= overlap_ratio(center, facecam)
    assert strategy == "geometric_candidates"
