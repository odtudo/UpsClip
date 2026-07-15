from __future__ import annotations

import json
import math
from pathlib import Path

import cv2

from .types import FaceDetection, Rect, SceneSegment, SmartLayoutError


def remap_detection_rect(values, scale: float) -> Rect:
    """Map YuNet analysis-resolution coordinates back to the source frame."""
    if scale <= 0:
        raise ValueError("Face analysis scale must be positive")
    x, y, width, height = (round(float(value) / scale) for value in values[:4])
    return Rect(x, y, width, height)


class OpenCVFaceDetector:
    """YuNet CPU detector with optional Haar fallback; never performs identification."""

    name = "opencv_yunet"

    def __init__(self, settings: object) -> None:
        self.settings = settings
        model = Path(settings.face_detector_model_path)
        if not model.is_file():
            raise SmartLayoutError(
                "YuNet face model missing. Run ./scripts/download_face_model.sh or rebuild Docker."
            )
        try:
            self.detector = cv2.FaceDetectorYN.create(
                str(model),
                "",
                (320, 320),
                settings.face_detector_profile_threshold,
                settings.face_detector_nms_threshold,
                settings.face_detector_top_k,
            )
        except cv2.error as exc:
            raise SmartLayoutError("YuNet face detector could not load its ONNX model") from exc
        self.haar = None
        if settings.face_detector_haar_fallback:
            cascade = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            fallback = cv2.CascadeClassifier(str(cascade))
            self.haar = None if fallback.empty() else fallback

    def detect(self, frame, timestamp: float) -> list[FaceDetection]:
        source_height, source_width = frame.shape[:2]
        scale = min(1.0, self.settings.face_analysis_max_width / source_width)
        analysis = (
            cv2.resize(frame, (round(source_width * scale), round(source_height * scale)))
            if scale < 1.0
            else frame
        )
        analysis_height, analysis_width = analysis.shape[:2]
        self.detector.setInputSize((analysis_width, analysis_height))
        _, faces = self.detector.detect(analysis)
        detections = []
        if faces is not None:
            for face in faces:
                region = remap_detection_rect(face, scale)
                detections.append(
                    FaceDetection(
                        timestamp,
                        region,
                        float(face[14]),
                        source_width,
                        source_height,
                        "yunet",
                    )
                )
        if not detections and self.haar is not None:
            gray = cv2.equalizeHist(cv2.cvtColor(analysis, cv2.COLOR_BGR2GRAY))
            boxes = self.haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
            for x, y, width, height in boxes:
                detections.append(
                    FaceDetection(
                        timestamp,
                        Rect(
                            round(int(x) / scale),
                            round(int(y) / scale),
                            round(int(width) / scale),
                            round(int(height) / scale),
                        ),
                        0.50,
                        source_width,
                        source_height,
                        "haar_fallback",
                    )
                )
        return sorted(detections, key=lambda item: (-item.confidence, -item.region.area))


def sample_faces(
    path: str,
    scene: SceneSegment,
    settings: object,
    detector: OpenCVFaceDetector,
    *,
    debug_dir: Path | None = None,
    sample_offset: int = 0,
) -> tuple[list[list[FaceDetection]], int, int, list[dict]]:
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise SmartLayoutError("Frame decode failed during face analysis")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    count = max(
        3,
        min(12, math.ceil((scene.end - scene.start) * settings.face_detection_sample_fps)),
    )
    margin = min(0.3, (scene.end - scene.start) / 4)
    start, end = scene.start + margin, max(scene.start + margin, scene.end - margin)
    timestamps = [start + (end - start) * index / max(1, count - 1) for index in range(count)]
    frames: list[list[FaceDetection]] = []
    records: list[dict] = []
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
    try:
        for index, timestamp in enumerate(timestamps):
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = capture.read()
            detections = detector.detect(frame, timestamp) if ok else []
            frames.append(detections)
            record = {
                "sample": sample_offset + index,
                "timestamp": round(timestamp, 3),
                "decoded": ok,
                "detections": [
                    {
                        "x": item.region.x,
                        "y": item.region.y,
                        "width": item.region.width,
                        "height": item.region.height,
                        "score": round(item.confidence, 4),
                        "area_ratio": round(item.area_ratio, 6),
                        "detector": item.detector,
                        "accepted": item.confidence >= settings.face_detector_score_threshold,
                        "discard_reason": (
                            None
                            if item.confidence >= settings.face_detector_score_threshold
                            else "below_normal_score_threshold"
                        ),
                    }
                    for item in detections
                ],
            }
            records.append(record)
            if debug_dir and ok:
                raw_path = debug_dir / f"frame_{sample_offset + index:03d}_raw.jpg"
                detection_path = debug_dir / f"frame_{sample_offset + index:03d}_detections.jpg"
                cv2.imwrite(str(raw_path), frame)
                annotated = frame.copy()
                for item in detections:
                    accepted = item.confidence >= settings.face_detector_score_threshold
                    color = (0, 200, 0) if accepted else (0, 220, 255)
                    region = item.region
                    cv2.rectangle(
                        annotated,
                        (region.x, region.y),
                        (region.x + region.width, region.y + region.height),
                        color,
                        3,
                    )
                    label = f"{item.detector} {item.confidence:.2f} area={item.area_ratio:.4f}"
                    cv2.putText(
                        annotated,
                        label,
                        (region.x, max(24, region.y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        color,
                        2,
                        cv2.LINE_AA,
                    )
                cv2.imwrite(str(detection_path), annotated)
    finally:
        capture.release()
    if debug_dir:
        (debug_dir / "face_detections.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    return frames, width, height, records
