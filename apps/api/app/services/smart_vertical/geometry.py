from __future__ import annotations

from statistics import median

from .types import Rect


def clamp_rect(rect: Rect, frame_width: int, frame_height: int, minimum: int = 2) -> Rect:
    if frame_width < minimum or frame_height < minimum:
        raise ValueError("Unsupported frame resolution")
    x = max(0, min(rect.x, frame_width - minimum))
    y = max(0, min(rect.y, frame_height - minimum))
    width = max(minimum, min(rect.width, frame_width - x))
    height = max(minimum, min(rect.height, frame_height - y))
    return Rect(x, y, width - width % 2, height - height % 2)


def expand_face(rect: Rect, frame_width: int, frame_height: int, settings: object) -> Rect:
    x = round(rect.x - rect.width * settings.facebox_expand_left)
    y = round(rect.y - rect.height * settings.facebox_expand_top)
    width = round(rect.width * (1 + settings.facebox_expand_left + settings.facebox_expand_right))
    height = round(rect.height * (1 + settings.facebox_expand_top + settings.facebox_expand_bottom))
    return clamp_rect(Rect(x, y, width, height), frame_width, frame_height)


def median_rect(rects: list[Rect]) -> Rect:
    if not rects:
        raise ValueError("No regions to stabilize")
    values = zip(*((r.x, r.y, r.width, r.height) for r in rects), strict=False)
    return Rect(*(round(median(items)) for items in values))


def iou(left: Rect, right: Rect) -> float:
    x1, y1 = max(left.x, right.x), max(left.y, right.y)
    x2 = min(left.x + left.width, right.x + right.width)
    y2 = min(left.y + left.height, right.y + right.height)
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = left.area + right.area - intersection
    return intersection / union if union else 0.0


def overlap_ratio(crop: Rect, excluded: Rect) -> float:
    x = max(0, min(crop.x + crop.width, excluded.x + excluded.width) - max(crop.x, excluded.x))
    y = max(0, min(crop.y + crop.height, excluded.y + excluded.height) - max(crop.y, excluded.y))
    return (x * y) / max(1, excluded.area)


def facecam_position(rect: Rect, width: int, height: int) -> str:
    cx, cy = rect.center[0] / width, rect.center[1] / height
    horizontal = "left" if cx < 0.35 else "right" if cx > 0.65 else "center"
    vertical = "top" if cy < 0.35 else "bottom" if cy > 0.65 else "center"
    if horizontal in {"left", "right"} and 0.35 <= cy <= 0.65:
        return f"{horizontal}_center"
    if horizontal != "center" and vertical != "center":
        return f"{vertical}_{horizontal}"
    return horizontal if horizontal != "center" else vertical if vertical != "center" else "center"


def side_facecam_region(face: Rect, width: int, height: int) -> Rect:
    """Stable column crop for large side cameras; excludes chat below when possible."""
    position = facecam_position(face, width, height)
    column_width = max(round(width * 0.22), round(face.width * 3.6))
    column_width = min(round(width * 0.35), column_width)
    x = 0 if position.startswith("left") else width - column_width
    y = max(0, round(face.y - face.height * 0.8))
    region_height = min(height - y, round(face.height * 3.0))
    return clamp_rect(Rect(x, y, column_width, region_height), width, height)


def aspect_crop(width: int, height: int, target_ratio: float, center_x: float | None = None) -> Rect:
    source_ratio = width / height
    if source_ratio > target_ratio:
        crop_width = min(width, round(height * target_ratio))
        x = round((center_x if center_x is not None else width / 2) - crop_width / 2)
        return clamp_rect(Rect(x, 0, crop_width, height), width, height)
    crop_height = min(height, round(width / target_ratio))
    return clamp_rect(Rect(0, round((height - crop_height) / 2), width, crop_height), width, height)


def select_content_crop(
    width: int, height: int, target_ratio: float, facecam: Rect | None, roi: Rect | None = None
) -> tuple[Rect, float, str]:
    if width / height >= target_ratio:
        crop_height = height
        crop_width = min(width, round(height * target_ratio))
    else:
        crop_width = width
        crop_height = min(height, round(width / target_ratio))
    if crop_height < height:
        y_positions = [0, (height - crop_height) // 2, height - crop_height]
        x_positions = [0]
    else:
        x_positions = [0, (width - crop_width) // 2, width - crop_width]
        y_positions = [0]
    candidates: list[tuple[float, float, Rect, str]] = []
    for x in sorted(set(x_positions)):
        for y in sorted(set(y_positions)):
            crop = clamp_rect(Rect(x, y, crop_width, crop_height), width, height)
            overlap = overlap_ratio(crop, facecam) if facecam else 0.0
            cx, cy = crop.center
            center_cost = abs(cx - width / 2) / width + abs(cy - height / 2) / height
            roi_bonus = iou(crop, roi) if roi else 0.0
            candidates.append((overlap * 4 + center_cost - roi_bonus, overlap, crop, "geometric_candidates"))
    _, overlap, crop, strategy = min(candidates, key=lambda item: item[0])
    return crop, overlap, strategy
