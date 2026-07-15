from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

LayoutMode = Literal["fullscreen_face", "small_facecam", "no_face", "uncertain"]


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2

    def dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class FaceDetection:
    timestamp: float
    region: Rect
    confidence: float
    frame_width: int
    frame_height: int
    detector: str = "yunet"

    @property
    def area_ratio(self) -> float:
        return self.region.area / (self.frame_width * self.frame_height)


@dataclass(frozen=True)
class SceneSegment:
    start: float
    end: float


@dataclass
class CompositionSegment:
    start: float
    end: float
    layout: LayoutMode
    confidence: float
    detection_source: str
    face_region: Rect | None = None
    facecam_region: Rect | None = None
    facecam_position: str | None = None
    output_crop: Rect | None = None
    content_crop: Rect | None = None
    duplicate_facecam_excluded: bool | None = None
    reasons: list[str] = field(default_factory=list)

    def dict(self) -> dict[str, Any]:
        value = asdict(self)
        return {key: item for key, item in value.items() if item is not None}


class SmartLayoutError(RuntimeError):
    pass


class ProfileValidationError(SmartLayoutError):
    pass


class CompositionPlanError(SmartLayoutError):
    pass


class VerticalRenderError(SmartLayoutError):
    pass
