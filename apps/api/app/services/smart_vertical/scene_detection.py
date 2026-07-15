from __future__ import annotations

import cv2
import numpy as np

from .types import SceneSegment, SmartLayoutError


def detect_scenes(path: str, duration: float, settings: object) -> tuple[list[SceneSegment], dict]:
    if not settings.scene_detection_enabled:
        return [SceneSegment(0.0, duration)], {"samples": 0, "changes": [], "scores": []}
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise SmartLayoutError("Scene analysis failed: video could not be opened")
    interval = 1.0 / max(0.2, settings.scene_sample_fps)
    previous = None
    changes: list[float] = []
    scores: list[dict[str, float]] = []
    samples = 0
    timestamp = 0.0
    try:
        while timestamp < duration:
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = capture.read()
            if not ok:
                timestamp += interval
                continue
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90))
            if previous is not None:
                score = float(np.mean(cv2.absdiff(previous, small)) / 255.0)
                scores.append({"timestamp": round(timestamp, 3), "score": round(score, 6)})
                if score >= settings.scene_change_threshold:
                    if not changes or timestamp - changes[-1] >= settings.scene_min_duration_seconds:
                        changes.append(timestamp)
            previous = small
            samples += 1
            timestamp += interval
    finally:
        capture.release()
    boundaries = [0.0, *changes, duration]
    pairs = zip(boundaries, boundaries[1:], strict=False)
    scenes = [SceneSegment(round(a, 3), round(b, 3)) for a, b in pairs if b > a]
    return merge_short_scenes(scenes, settings.scene_min_duration_seconds), {
        "samples": samples,
        "changes": changes,
        "scores": scores,
    }


def merge_short_scenes(scenes: list[SceneSegment], minimum: float) -> list[SceneSegment]:
    merged: list[SceneSegment] = []
    for scene in scenes:
        if merged and scene.end - scene.start < minimum:
            previous = merged.pop()
            merged.append(SceneSegment(previous.start, scene.end))
        else:
            merged.append(scene)
    return merged
