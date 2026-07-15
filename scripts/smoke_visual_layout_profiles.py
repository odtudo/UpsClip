#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from apps.api.app.config import Settings
from apps.api.app.services.smart_vertical.face_detection import OpenCVFaceDetector
from apps.api.app.services.smart_vertical.types import FaceDetection, Rect, SmartLayoutError
from apps.api.app.services.vod_analysis.visual_profiles import ProfileLayoutMatcher


def fallback_faces(name: str) -> list[FaceDetection]:
    if name.startswith("full"):
        return [FaceDetection(0, Rect(638, 279, 251, 373), 0.95, 1920, 1080)]
    if name.startswith("gameplay"):
        return [FaceDetection(0, Rect(115, 400, 190, 230), 0.95, 1920, 1080)]
    return [FaceDetection(0, Rect(500, 120, 700, 760), 0.95, 1920, 1080)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test IlloJuan OBS layout profile matching")
    parser.add_argument("--output", type=Path, default=Path("data/analysis/smoke_visual_profiles"))
    args = parser.parse_args()
    settings = Settings()
    matcher = ProfileLayoutMatcher(
        settings.visual_layout_profile_path, settings.face_detector_score_threshold
    )
    references = settings.visual_layout_profile_path.parent / "illojuan"
    images = {
        "full_camera_real": cv2.imread(str(references / "full_camera_01.jpg")),
        "gameplay_real": cv2.imread(str(references / "gameplay_left_01.jpg")),
        "gameplay_small_real": cv2.imread(str(references / "gameplay_small_left_01.jpg")),
    }
    gameplay = images["gameplay_real"]
    images["waiting_person_photo"] = cv2.resize(gameplay[:, 500:], (gameplay.shape[1], gameplay.shape[0]))
    try:
        detector = OpenCVFaceDetector(settings)
    except SmartLayoutError:
        detector = None
    expected = {
        "waiting_person_photo": "waiting_or_music",
        "full_camera_real": "talking",
        "gameplay_real": "gameplay",
        "gameplay_small_real": "gameplay",
    }
    results = {}
    args.output.mkdir(parents=True, exist_ok=True)
    for name, image in images.items():
        if image is None:
            raise RuntimeError(f"Smoke asset is missing: {name}")
        faces = detector.detect(image, 0) if detector else fallback_faces(name)
        match = matcher.match(image, faces)
        results[name] = match.model_dump(mode="json")
        if match.phase != expected[name]:
            raise AssertionError(
                f"{name}: expected {expected[name]}, got {match.phase} "
                f"({match.layout_id}, {match.match_score:.3f})"
            )
        cv2.imwrite(str(args.output / f"{name}.jpg"), image)
    (args.output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                name: {
                    "phase": value["phase"],
                    "layout_id": value["layout_id"],
                    "score": value["match_score"],
                }
                for name, value in results.items()
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
