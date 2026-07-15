from __future__ import annotations

import hashlib
import json
import time
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from ..media import media_duration, probe_media
from .classifier import classify_scene
from .face_detection import OpenCVFaceDetector, sample_faces
from .geometry import aspect_crop, facecam_position, iou, select_content_crop
from .profiles import normalize_identity, resolve_profile, scaled_profile_regions
from .scene_detection import detect_scenes
from .types import CompositionPlanError, CompositionSegment, Rect


def build_composition_plan(
    source: Path,
    destination: Path,
    *,
    requested_profile: str,
    uploader: str | None,
    settings: object,
    progress: Callable[[str, int, str], None] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    info = probe_media(source, settings)
    video = next((item for item in info["streams"] if item.get("codec_type") == "video"), None)
    if not video:
        raise CompositionPlanError("Smart layout requires a video stream")
    width, height = int(video["width"]), int(video["height"])
    frame_rate = _frame_rate(video)
    duration = media_duration(source, settings)
    profile, profile_reason = resolve_profile(settings.data_dir / "profiles", requested_profile, uploader)
    if progress:
        progress("detecting_scenes", 39, "Detecting scene changes")
    scene_started = time.monotonic()
    scenes, scene_debug = detect_scenes(str(source), duration, settings)
    scene_seconds = time.monotonic() - scene_started
    detector = OpenCVFaceDetector(settings)
    debug_dir = destination.parent / "smart_vertical_debug" if settings.smart_layout_debug else None
    segments: list[CompositionSegment] = []
    warnings: list[dict[str, Any]] = []
    detection_records: list[dict[str, Any]] = []
    face_started = time.monotonic()
    for index, scene in enumerate(scenes):
        if progress:
            progress(
                "analyzing_layouts",
                43 + round(12 * index / max(1, len(scenes))),
                "Analyzing video layouts and facecam",
            )
        frames, frame_width, frame_height, records = sample_faces(
            str(source),
            scene,
            settings,
            detector,
            debug_dir=debug_dir,
            sample_offset=len(detection_records),
        )
        detection_records.extend(records)
        segment = classify_scene(scene, frames, frame_width, frame_height, settings)
        if (
            segment.layout in {"fullscreen_face", "small_facecam"}
            and segment.confidence < settings.face_layout_min_confidence
        ):
            segment.layout = "uncertain"
            segment.reasons.append("below_layout_confidence_threshold")
        _apply_profile(segment, profile, frame_width, frame_height, frames, settings)
        _finalize_geometry(segment, frame_width, frame_height, settings, profile)
        if segment.layout in {"no_face", "uncertain"}:
            warnings.append(
                {
                    "code": "face_not_detected" if segment.layout == "no_face" else "layout_uncertain",
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "message": "No reliable facecam was detected; a simple vertical crop was used.",
                }
            )
        elif segment.detection_source == "profile_fallback":
            warnings.append(
                {
                    "code": "profile_facecam_fallback",
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "message": (
                        "Automatic face detection was uncertain; the "
                        f"{profile.get('display_name', profile['id'])} profile was used."
                    ),
                }
            )
        if segment.layout == "small_facecam" and not segment.duplicate_facecam_excluded:
            warnings.append(
                {
                    "code": "duplicate_facecam_visible",
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "message": "The original facecam may remain visible in the content crop.",
                }
            )
        segments.append(segment)
    face_seconds = time.monotonic() - face_started
    segments = stabilize_layouts(segments, settings)
    segments = validate_segments(segments, duration, width, height)
    counts = {
        name: sum(item.layout == name for item in segments)
        for name in ("fullscreen_face", "small_facecam", "no_face", "uncertain")
    }
    resolved = profile["id"] if profile else None
    plan = {
        "version": 1,
        "algorithm_version": "smart_vertical_v2_yunet",
        "debug_enabled": settings.smart_layout_debug,
        "source": {
            "width": width,
            "height": height,
            "duration": round(duration, 3),
            "frame_rate": frame_rate,
            "fingerprint": _fingerprint(source),
        },
        "output": {"width": settings.vertical_output_width, "height": settings.vertical_output_height},
        "smart_vertical_layout": True,
        "profile_requested": requested_profile,
        "profile_resolved": resolved,
        "profile_resolution_reason": profile_reason,
        "uploader_original": uploader,
        "uploader_normalized": normalize_identity(uploader),
        "segments": [item.dict() for item in segments],
        "warnings": warnings,
        "summary": {
            "segments": len(segments),
            **counts,
            "fallbacks": counts["no_face"] + counts["uncertain"],
        },
        "analysis": {
            "scene_samples": scene_debug["samples"],
            "face_frames_analyzed": len(detection_records),
            "faces_detected": sum(len(item["detections"]) for item in detection_records),
            "faces_above_normal_threshold": sum(
                sum(bool(face["accepted"]) for face in item["detections"]) for item in detection_records
            ),
            "detector": detector.name,
            "analysis_max_width": settings.face_analysis_max_width,
            "scene_detection_seconds": round(scene_seconds, 3),
            "face_detection_seconds": round(face_seconds, 3),
            "planning_seconds": round(time.monotonic() - started, 3),
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    (destination.parent / "scene_analysis.json").write_text(
        json.dumps({"segments": [vars(item) for item in scenes], **scene_debug}, indent=2),
        encoding="utf-8",
    )
    (destination.parent / "face_detections.json").write_text(
        json.dumps(detection_records, indent=2), encoding="utf-8"
    )
    if debug_dir:
        _annotate_final_debug(debug_dir, detection_records, segments)
    return plan


def _apply_profile(
    segment: CompositionSegment,
    profile: dict | None,
    width: int,
    height: int,
    frames: list[list],
    settings: object,
) -> None:
    if not profile:
        return
    detections = [face for group in frames for face in group]
    for region, layout in scaled_profile_regions(profile, width, height):
        matches = [
            item
            for item in detections
            if item.confidence >= settings.face_detector_profile_threshold
            and (iou(region, item.region) > 0.05 or _contains(region, item.region.center))
        ]
        if matches and segment.layout == "small_facecam":
            segment.facecam_region = region
            segment.facecam_position = layout.get("position") or facecam_position(region, width, height)
            segment.detection_source = "profile_adjusted"
            segment.reasons.append("automatic_face_matched_profile_region")
            return
        if matches and segment.layout in {"uncertain", "no_face"}:
            segment.layout = "small_facecam"
            segment.confidence = max(segment.confidence, 0.62)
            segment.facecam_region = region
            segment.facecam_position = layout.get("position") or facecam_position(region, width, height)
            segment.detection_source = "profile_fallback"
            segment.reasons.append("face_inside_profile_region")
            return


def _contains(rect: Rect, point: tuple[float, float]) -> bool:
    return rect.x <= point[0] <= rect.x + rect.width and rect.y <= point[1] <= rect.y + rect.height


def _finalize_geometry(
    segment: CompositionSegment, width: int, height: int, settings: object, profile: dict | None
) -> None:
    target = settings.vertical_output_width / settings.vertical_output_height
    if segment.layout == "fullscreen_face" and segment.face_region:
        segment.output_crop = aspect_crop(width, height, target, segment.face_region.center[0])
    elif segment.layout == "small_facecam" and segment.facecam_region:
        roi = None
        if profile:
            raw_roi = None
            for region, layout in scaled_profile_regions(profile, width, height):
                if iou(region, segment.facecam_region) >= 0.5:
                    raw_roi = layout.get("content_region_of_interest")
                    break
            raw_roi = raw_roi or (profile.get("vertical") or {}).get("content_region_of_interest")
            if raw_roi:
                source = profile["source_resolution"]
                roi = Rect(
                    round(raw_roi["x"] * width / source["width"]),
                    round(raw_roi["y"] * height / source["height"]),
                    round(raw_roi["width"] * width / source["width"]),
                    round(raw_roi["height"] * height / source["height"]),
                )
        lower_height = settings.vertical_output_height * (1 - settings.vertical_facecam_height_ratio)
        crop, overlap, strategy = select_content_crop(
            width, height, settings.vertical_output_width / lower_height, segment.facecam_region, roi
        )
        segment.content_crop = crop
        segment.duplicate_facecam_excluded = overlap < 0.05
        segment.reasons.append(f"content_crop_{strategy}")
    else:
        segment.output_crop = aspect_crop(width, height, target)


def _annotate_final_debug(
    debug_dir: Path, records: list[dict[str, Any]], segments: list[CompositionSegment]
) -> None:
    import cv2

    for record in records:
        index = record["sample"]
        raw = cv2.imread(str(debug_dir / f"frame_{index:03d}_raw.jpg"))
        if raw is None:
            continue
        segment = next((item for item in segments if item.start <= record["timestamp"] <= item.end), None)
        if segment is None:
            continue
        for rect, color, label in (
            (segment.facecam_region, (0, 255, 0), "FACECAM"),
            (segment.face_region, (0, 0, 255), "FACE EXPANDED"),
            (segment.content_crop, (255, 150, 0), "CONTENT CROP"),
            (segment.output_crop, (255, 0, 255), "OUTPUT CROP"),
        ):
            if rect:
                cv2.rectangle(
                    raw,
                    (rect.x, rect.y),
                    (rect.x + rect.width, rect.y + rect.height),
                    color,
                    4,
                )
                cv2.putText(
                    raw,
                    label,
                    (rect.x + 5, max(28, rect.y + 28)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    color,
                    2,
                    cv2.LINE_AA,
                )
        cv2.putText(
            raw,
            f"{segment.layout} {segment.confidence:.2f} {segment.detection_source}",
            (20, raw.shape[0] - 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.imwrite(str(debug_dir / f"frame_{index:03d}_final.jpg"), raw)


def stabilize_layouts(segments: list[CompositionSegment], settings: object) -> list[CompositionSegment]:
    if not segments:
        return []
    for index, item in enumerate(segments):
        duration = item.end - item.start
        if (
            item.layout == "uncertain"
            and duration < settings.layout_min_segment_seconds
            and index > 0
            and index + 1 < len(segments)
        ):
            if segments[index - 1].layout == segments[index + 1].layout:
                neighbor = segments[index - 1]
                item.layout = neighbor.layout
                item.facecam_region = neighbor.facecam_region
                item.facecam_position = neighbor.facecam_position
                item.content_crop = neighbor.content_crop
                item.output_crop = neighbor.output_crop
                item.duplicate_facecam_excluded = neighbor.duplicate_facecam_excluded
                item.detection_source = "hysteresis"
                item.reasons.append("short_uncertain_segment_bridged")
    merged = [segments[0]]
    for item in segments[1:]:
        previous = merged[-1]
        compatible_regions = True
        if previous.facecam_region and item.facecam_region:
            px, py = previous.facecam_region.center
            ix, iy = item.facecam_region.center
            diagonal = (previous.facecam_region.width**2 + previous.facecam_region.height**2) ** 0.5
            center_distance = ((px - ix) ** 2 + (py - iy) ** 2) ** 0.5 / max(1, diagonal)
            compatible_regions = (
                iou(previous.facecam_region, item.facecam_region) >= settings.layout_merge_iou_threshold
                or center_distance <= settings.layout_merge_center_distance_ratio
            )
        if previous.layout == item.layout and compatible_regions:
            previous.end = item.end
            previous.confidence = round((previous.confidence + item.confidence) / 2, 3)
            previous.reasons = sorted(set(previous.reasons + item.reasons))
        else:
            merged.append(item)
    return merged


def validate_segments(
    segments: list[CompositionSegment], duration: float, width: int, height: int
) -> list[CompositionSegment]:
    if not segments:
        raise CompositionPlanError("Composition plan has no segments")
    cursor = 0.0
    for item in segments:
        if item.start < cursor - 0.02 or item.end <= item.start:
            raise CompositionPlanError("Composition plan contains invalid segment times")
        if abs(item.start - cursor) <= 0.15:
            item.start = cursor
        elif item.start > cursor:
            raise CompositionPlanError("Composition plan contains an uncovered gap")
        cursor = item.end
        for rect in (item.face_region, item.facecam_region, item.output_crop, item.content_crop):
            if rect and (
                rect.x < 0
                or rect.y < 0
                or rect.width <= 0
                or rect.height <= 0
                or rect.x + rect.width > width
                or rect.y + rect.height > height
            ):
                raise CompositionPlanError("Composition plan contains an invalid region")
    if abs(cursor - duration) > 0.2:
        raise CompositionPlanError("Composition plan does not cover the edited duration")
    segments[-1].end = duration
    return segments


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    return hashlib.sha256(f"{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()[:16]


def _frame_rate(video: dict[str, Any]) -> float:
    try:
        rate = float(Fraction(video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1"))
    except (ValueError, ZeroDivisionError):
        rate = 30.0
    if not 1 <= rate <= 120:
        return 30.0
    return round(rate, 3)
