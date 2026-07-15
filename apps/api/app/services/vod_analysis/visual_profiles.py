from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, Field, model_validator

from ..smart_vertical.types import FaceDetection, Rect


class ProfileRegion(BaseModel):
    id: str
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    weight: float = Field(default=1, gt=0)


class AreaRange(BaseModel):
    min: float = Field(ge=0, le=1)
    max: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def ordered(self) -> "AreaRange":
        if self.max <= self.min:
            raise ValueError("Face area maximum must exceed minimum")
        return self


class Resolution(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class VisualLayoutDefinition(BaseModel):
    id: str
    phase: Literal["talking", "gameplay"]
    source_resolution: Resolution
    expected_face_region: ProfileRegion
    expected_webcam_region: ProfileRegion | None = None
    expected_face_area_ratio: AreaRange
    expected_position: str
    stable_background_regions: list[ProfileRegion] = Field(default_factory=list)
    reference_images: list[str] = Field(min_length=1)
    weights: dict[str, float]
    minimum_match_score: float = Field(ge=0, le=1)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_layout(self) -> "VisualLayoutDefinition":
        required = {
            "face_position",
            "face_size",
            "background_similarity",
            "reference_similarity",
            "temporal_stability",
        }
        if set(self.weights) != required or any(value < 0 for value in self.weights.values()):
            raise ValueError("Layout weights are incomplete or negative")
        if not math.isclose(sum(self.weights.values()), 1.0, abs_tol=1e-6):
            raise ValueError("Layout weights must sum to 1")
        for region in [self.expected_face_region, *self.stable_background_regions]:
            if (
                region.x + region.width > self.source_resolution.width
                or region.y + region.height > self.source_resolution.height
            ):
                raise ValueError(f"Region '{region.id}' exceeds source resolution")
        return self


class VisualLayoutProfile(BaseModel):
    version: int = 1
    id: str
    display_name: str
    ambiguity_margin: float = Field(default=0.08, ge=0, le=1)
    minimum_frame_sharpness: float = Field(default=12, ge=0)
    layouts: list[VisualLayoutDefinition]

    @model_validator(mode="after")
    def unique_layouts(self) -> "VisualLayoutProfile":
        ids = [item.id for item in self.layouts]
        if len(ids) != len(set(ids)):
            raise ValueError("Visual layout ids must be unique")
        return self


class LayoutMatch(BaseModel):
    layout_id: str
    phase: Literal["waiting_or_music", "talking", "gameplay", "unknown"]
    match_score: float = Field(ge=0, le=1)
    second_best_score: float = Field(ge=0, le=1)
    score_margin: float = Field(ge=0, le=1)
    matched_reference: str | None = None
    face_box: dict[str, int] | None = None
    face_area_ratio: float = Field(default=0, ge=0, le=1)
    face_position: str | None = None
    signals: dict[str, float] = Field(default_factory=dict)
    background_region_scores: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def load_visual_profile(path: Path) -> VisualLayoutProfile:
    try:
        profile = VisualLayoutProfile.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Visual layout profile does not exist: {path}") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"Visual layout profile is invalid: {exc}") from exc
    for layout in profile.layouts:
        if not layout.enabled:
            continue
        for name in layout.reference_images:
            reference = resolve_reference(path, name)
            if not reference.is_file():
                raise ValueError(f"Visual layout reference does not exist: {name}")
            if cv2.imread(str(reference)) is None:
                raise ValueError(f"Visual layout reference cannot be decoded: {name}")
    return profile


def resolve_reference(profile_path: Path, name: str) -> Path:
    candidate = (profile_path.parent / name).resolve()
    root = profile_path.parent.resolve()
    if root != candidate.parent and root not in candidate.parents:
        raise ValueError("Visual reference path escapes the profile directory")
    return candidate


def visual_profile_fingerprint(path: Path) -> str:
    profile = load_visual_profile(path)
    digest = hashlib.sha256(path.read_bytes())
    for layout in sorted(profile.layouts, key=lambda item: item.id):
        if not layout.enabled:
            continue
        for name in sorted(layout.reference_images):
            digest.update(name.encode())
            digest.update(resolve_reference(path, name).read_bytes())
    return digest.hexdigest()


class ProfileLayoutMatcher:
    def __init__(self, profile_path: Path, detector_threshold: float):
        self.profile_path = profile_path
        self.profile = load_visual_profile(profile_path)
        self.detector_threshold = detector_threshold
        self.references: dict[str, list[tuple[str, np.ndarray]]] = {}
        self.previous_frame: np.ndarray | None = None
        for layout in self.profile.layouts:
            if not layout.enabled:
                continue
            loaded = []
            for name in layout.reference_images:
                image = cv2.imread(str(resolve_reference(profile_path, name)))
                if image is None:
                    raise ValueError(f"Visual layout reference cannot be decoded: {name}")
                loaded.append((name, image))
            self.references[layout.id] = loaded

    def match(self, frame: np.ndarray | None, detections: list[FaceDetection]) -> LayoutMatch:
        if frame is None:
            return LayoutMatch(
                layout_id="unknown",
                phase="unknown",
                match_score=0,
                second_best_score=0,
                score_margin=0,
                reasons=["frame_decode_failed"],
                warnings=["visual_frame_unavailable"],
            )
        sharpness = float(cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
        if sharpness < self.profile.minimum_frame_sharpness:
            return LayoutMatch(
                layout_id="unknown",
                phase="unknown",
                match_score=0,
                second_best_score=0,
                score_margin=0,
                signals={"frame_sharpness": sharpness},
                reasons=["frame_quality_too_low"],
            )
        candidates = []
        for layout in self.profile.layouts:
            if layout.enabled:
                candidates.append(self._score_layout(frame, detections, layout))
        candidates.sort(key=lambda item: item.match_score, reverse=True)
        if not candidates:
            return self._waiting(sharpness, "no_enabled_layouts")
        best = candidates[0]
        second = candidates[1].match_score if len(candidates) > 1 else 0.0
        margin = max(0.0, best.match_score - second)
        best.second_best_score = second
        best.score_margin = margin
        best.signals["frame_sharpness"] = sharpness
        self.previous_frame = frame.copy()
        definition = next(item for item in self.profile.layouts if item.id == best.layout_id)
        if best.match_score < definition.minimum_match_score:
            waiting = self._waiting(sharpness, "no_known_layout_above_threshold")
            waiting.match_score = best.match_score
            waiting.second_best_score = second
            waiting.score_margin = margin
            waiting.matched_reference = best.matched_reference
            waiting.face_box = best.face_box
            waiting.face_area_ratio = best.face_area_ratio
            waiting.face_position = best.face_position
            waiting.signals.update(best.signals)
            waiting.signals["best_rejected_score"] = best.match_score
            waiting.background_region_scores = best.background_region_scores
            waiting.reasons.append(f"rejected_{best.layout_id}")
            return waiting
        if len(candidates) > 1 and margin < self.profile.ambiguity_margin:
            if candidates[1].phase == best.phase:
                best.reasons.extend(
                    [
                        "same_phase_layout_tie_resolved",
                        "known_layout_matched",
                        f"matched_{best.layout_id}",
                    ]
                )
                return best
            return LayoutMatch(
                layout_id="unknown",
                phase="unknown",
                match_score=best.match_score,
                second_best_score=second,
                score_margin=margin,
                matched_reference=best.matched_reference,
                face_box=best.face_box,
                face_area_ratio=best.face_area_ratio,
                face_position=best.face_position,
                signals=best.signals,
                background_region_scores=best.background_region_scores,
                reasons=["layout_scores_ambiguous"],
            )
        best.reasons.extend(["known_layout_matched", f"matched_{best.layout_id}"])
        return best

    def _waiting(self, sharpness: float, reason: str) -> LayoutMatch:
        self.previous_frame = None
        return LayoutMatch(
            layout_id="waiting_unmatched",
            phase="waiting_or_music",
            match_score=0,
            second_best_score=0,
            score_margin=0,
            signals={"frame_sharpness": sharpness},
            reasons=[reason, "valid_frame_unmatched_is_waiting"],
        )

    def _score_layout(
        self, frame: np.ndarray, detections: list[FaceDetection], layout: VisualLayoutDefinition
    ) -> LayoutMatch:
        height, width = frame.shape[:2]
        face_region = _scaled(layout.expected_face_region, width, height, layout.source_resolution)
        accepted = [item for item in detections if item.confidence >= self.detector_threshold]
        selected = max(accepted, key=lambda item: _face_region_score(item, face_region), default=None)
        face_position = _face_region_score(selected, face_region) if selected else 0.0
        face_size = (
            _face_size_score(selected.area_ratio, layout.expected_face_area_ratio) if selected else 0.0
        )
        region_scores: dict[str, float] = {}
        best_reference = None
        best_reference_score = 0.0
        best_background = 0.0
        for reference_name, reference in self.references[layout.id]:
            reference_score = _layout_similarity(frame, reference, layout.expected_webcam_region, layout)
            weighted_regions = []
            for region in layout.stable_background_regions:
                current_crop = _crop(frame, _scaled(region, width, height, layout.source_resolution))
                reference_crop = _crop(
                    reference,
                    _scaled(region, reference.shape[1], reference.shape[0], layout.source_resolution),
                )
                score = _image_similarity(current_crop, reference_crop)
                region_scores[f"{reference_name}:{region.id}"] = score
                weighted_regions.append((score, region.weight))
            background = (
                sum(score * weight for score, weight in weighted_regions)
                / sum(weight for _, weight in weighted_regions)
                if weighted_regions
                else reference_score
            )
            combined = reference_score * 0.55 + background * 0.45
            if combined > best_reference_score * 0.55 + best_background * 0.45:
                best_reference_score = reference_score
                best_background = background
                best_reference = reference_name
        temporal = _image_similarity(frame, self.previous_frame) if self.previous_frame is not None else 0.5
        signals = {
            "face_position": face_position,
            "face_size": face_size,
            "background_similarity": best_background,
            "reference_similarity": best_reference_score,
            "temporal_stability": temporal,
        }
        score = sum(signals[name] * layout.weights[name] for name in layout.weights)
        return LayoutMatch(
            layout_id=layout.id,
            phase=layout.phase,
            match_score=max(0.0, min(1.0, score)),
            second_best_score=0,
            score_margin=0,
            matched_reference=best_reference,
            face_box=selected.region.dict() if selected else None,
            face_area_ratio=selected.area_ratio if selected else 0,
            face_position=layout.expected_position if selected else None,
            signals=signals,
            background_region_scores=region_scores,
            reasons=["profile_layout_scored", "face_signal_secondary"],
        )


def _scaled(region: ProfileRegion, width: int, height: int, source: Resolution) -> Rect:
    return Rect(
        round(region.x * width / source.width),
        round(region.y * height / source.height),
        max(1, round(region.width * width / source.width)),
        max(1, round(region.height * height / source.height)),
    )


def _crop(image: np.ndarray, rect: Rect) -> np.ndarray:
    return image[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width]


def _face_region_score(detection: FaceDetection | None, expected: Rect) -> float:
    if detection is None:
        return 0.0
    cx, cy = detection.region.center
    ex, ey = expected.center
    distance = math.hypot(cx - ex, cy - ey) / max(1, math.hypot(expected.width, expected.height))
    inside = (
        expected.x <= cx <= expected.x + expected.width and expected.y <= cy <= expected.y + expected.height
    )
    return max(0.0, min(1.0, math.exp(-distance * 4) * (1.0 if inside else 0.45)))


def _face_size_score(value: float, expected: AreaRange) -> float:
    if expected.min <= value <= expected.max:
        return 1.0
    distance = expected.min - value if value < expected.min else value - expected.max
    return max(0.0, 1.0 - distance / max(expected.max - expected.min, 0.01))


def _layout_similarity(
    current: np.ndarray,
    reference: np.ndarray,
    region: ProfileRegion | None,
    layout: VisualLayoutDefinition,
) -> float:
    if region is None:
        return _image_similarity(current, reference)
    return _image_similarity(
        _crop(current, _scaled(region, current.shape[1], current.shape[0], layout.source_resolution)),
        _crop(reference, _scaled(region, reference.shape[1], reference.shape[0], layout.source_resolution)),
    )


def _image_similarity(first: np.ndarray | None, second: np.ndarray | None) -> float:
    if first is None or second is None or first.size == 0 or second.size == 0:
        return 0.0
    first = cv2.resize(first, (160, 90), interpolation=cv2.INTER_AREA)
    second = cv2.resize(second, (160, 90), interpolation=cv2.INTER_AREA)
    hsv_a, hsv_b = cv2.cvtColor(first, cv2.COLOR_BGR2HSV), cv2.cvtColor(second, cv2.COLOR_BGR2HSV)
    hist_a = cv2.calcHist([hsv_a], [0, 1], None, [24, 16], [0, 180, 0, 256])
    hist_b = cv2.calcHist([hsv_b], [0, 1], None, [24, 16], [0, 180, 0, 256])
    cv2.normalize(hist_a, hist_a)
    cv2.normalize(hist_b, hist_b)
    histogram = max(0.0, min(1.0, (cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL) + 1) / 2))
    gray_a, gray_b = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY), cv2.cvtColor(second, cv2.COLOR_BGR2GRAY)
    hash_a = cv2.resize(gray_a, (17, 16))[:, 1:] > cv2.resize(gray_a, (17, 16))[:, :-1]
    hash_b = cv2.resize(gray_b, (17, 16))[:, 1:] > cv2.resize(gray_b, (17, 16))[:, :-1]
    perceptual = 1.0 - float(np.count_nonzero(hash_a != hash_b)) / hash_a.size
    edges_a, edges_b = cv2.Canny(gray_a, 60, 140), cv2.Canny(gray_b, 60, 140)
    edge = 1.0 - min(1.0, float(np.mean(cv2.absdiff(edges_a, edges_b))) / 255)
    return histogram * 0.45 + perceptual * 0.35 + edge * 0.20


def dump_profile(path: Path, profile: VisualLayoutProfile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)


def profile_summary(path: Path) -> dict:
    profile = load_visual_profile(path)
    return {
        "id": profile.id,
        "version": profile.version,
        "enabled_layouts": [item.id for item in profile.layouts if item.enabled],
        "fingerprint": visual_profile_fingerprint(path),
    }
