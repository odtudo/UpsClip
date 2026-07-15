from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median, pstdev

from .geometry import expand_face, facecam_position, median_rect, side_facecam_region
from .types import CompositionSegment, FaceDetection, SceneSegment


@dataclass
class _Track:
    detections: list[FaceDetection] = field(default_factory=list)
    frame_indexes: set[int] = field(default_factory=set)


def classify_scene(
    scene: SceneSegment,
    frames: list[list[FaceDetection]],
    width: int,
    height: int,
    settings: object,
) -> CompositionSegment:
    accepted_frames = [
        [item for item in items if item.confidence >= settings.face_detector_score_threshold]
        for items in frames
    ]
    tracks = _cluster_detections(accepted_frames, width, height)
    if not tracks:
        return CompositionSegment(
            scene.start,
            scene.end,
            "no_face",
            0.8,
            "automatic",
            reasons=["no_face_above_normal_threshold"],
        )
    ranked = sorted(
        tracks,
        key=lambda track: _track_score(track, len(frames), width, height),
        reverse=True,
    )
    selected = ranked[0]
    candidates = selected.detections
    presence = len(selected.frame_indexes) / max(1, len(frames))
    centers_x = [item.region.center[0] / width for item in candidates]
    centers_y = [item.region.center[1] / height for item in candidates]
    areas = [item.area_ratio for item in candidates]
    position_spread = (pstdev(centers_x) if len(centers_x) > 1 else 0) + (
        pstdev(centers_y) if len(centers_y) > 1 else 0
    )
    size_spread = pstdev(areas) / max(median(areas), 1e-6) if len(areas) > 1 else 0
    stable = (
        position_spread <= settings.face_stability_position_tolerance * 2
        and size_spread <= settings.face_stability_size_tolerance
    )
    region = median_rect([item.region for item in candidates])
    expanded = expand_face(region, width, height, settings)
    position = facecam_position(region, width, height)
    face_area = median(areas)
    dominant_margin = (
        _track_score(ranked[0], len(frames), width, height)
        - _track_score(ranked[1], len(frames), width, height)
        if len(ranked) > 1
        else 1.0
    )
    reasons = [
        f"face_present_in_{len(selected.frame_indexes)}_of_{len(frames)}_frames",
        f"selected_track_margin_{dominant_margin:.3f}",
    ]
    side = position in {"left", "right", "left_center", "right_center"}
    if presence >= 0.55 and stable and side and face_area <= 0.15:
        confidence = min(1.0, 0.55 + presence * 0.3 + min(0.1, face_area * 5))
        return CompositionSegment(
            scene.start,
            scene.end,
            "small_facecam",
            confidence,
            "automatic_side_facecam",
            facecam_region=side_facecam_region(region, width, height),
            facecam_position="left_column" if position.startswith("left") else "right_column",
            reasons=[*reasons, "stable_side_face", "large_lateral_layout_supported"],
        )
    central = position == "center"
    if presence >= 0.55 and stable and face_area >= settings.fullscreen_face_area_threshold and central:
        confidence = min(1.0, 0.55 + presence * 0.25 + min(face_area, 0.2))
        return CompositionSegment(
            scene.start,
            scene.end,
            "fullscreen_face",
            confidence,
            "automatic",
            face_region=expanded,
            reasons=[*reasons, "large_stable_face", "central_face"],
        )
    edge_position = position != "center"
    if presence >= 0.6 and stable and edge_position:
        confidence = min(1.0, 0.50 + presence * 0.3 + max(0, 0.1 - position_spread))
        return CompositionSegment(
            scene.start,
            scene.end,
            "small_facecam",
            confidence,
            "automatic",
            facecam_region=expanded,
            facecam_position=position,
            reasons=[*reasons, "stable_edge_face", "overlay_facecam"],
        )
    return CompositionSegment(
        scene.start,
        scene.end,
        "uncertain",
        max(0.2, presence * 0.55),
        "automatic",
        face_region=expanded,
        reasons=[*reasons, "unstable_or_threshold_ambiguous"],
    )


def _cluster_detections(frames: list[list[FaceDetection]], width: int, height: int) -> list[_Track]:
    tracks: list[_Track] = []
    for frame_index, detections in enumerate(frames):
        for detection in detections:
            cx = detection.region.center[0] / width
            cy = detection.region.center[1] / height
            best: _Track | None = None
            best_distance = 1.0
            for track in tracks:
                if frame_index in track.frame_indexes:
                    continue
                last = track.detections[-1]
                distance = (
                    (cx - last.region.center[0] / width) ** 2 + (cy - last.region.center[1] / height) ** 2
                ) ** 0.5
                size_ratio = detection.region.area / max(1, last.region.area)
                if distance < 0.10 and 0.35 <= size_ratio <= 2.8 and distance < best_distance:
                    best, best_distance = track, distance
            if best is None:
                best = _Track()
                tracks.append(best)
            best.detections.append(detection)
            best.frame_indexes.add(frame_index)
    return tracks


def _track_score(track: _Track, frame_count: int, width: int, height: int) -> float:
    presence = len(track.frame_indexes) / max(1, frame_count)
    confidence = median(item.confidence for item in track.detections)
    area = median(item.area_ratio for item in track.detections)
    centers = [(item.region.center[0] / width, item.region.center[1] / height) for item in track.detections]
    spread = 0.0
    if len(centers) > 1:
        spread = pstdev(item[0] for item in centers) + pstdev(item[1] for item in centers)
    return presence * 1.2 + confidence * 0.5 + min(area * 12, 0.5) - spread * 2
