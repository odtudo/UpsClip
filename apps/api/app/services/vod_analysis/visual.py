from pathlib import Path

import cv2
import numpy as np

from ...config import Settings
from ..process import run_command


def extract_visual_samples(
    stream_url: str,
    start: float,
    duration: float,
    count: int,
    directory: Path,
    settings: Settings,
    *,
    user_agent: str | None = None,
    referer: str | None = None,
) -> list[Path]:
    if count <= 0:
        return []
    directory.mkdir(parents=True, exist_ok=True)
    pattern = directory / "frame_%02d.jpg"
    fps = count / max(duration, 0.1)
    input_options: list[str] = []
    if user_agent:
        input_options.extend(["-user_agent", user_agent])
    if referer:
        input_options.extend(["-referer", referer])
    run_command(
        [
            settings.ffmpeg_path,
            "-y",
            "-ss",
            f"{start:.3f}",
            *input_options,
            "-i",
            stream_url,
            "-t",
            f"{duration:.3f}",
            "-an",
            "-vf",
            f"fps={fps:.6f},scale=320:-2",
            "-frames:v",
            str(count),
            "-q:v",
            "5",
            pattern,
        ],
        label="Coarse visual sample extraction",
        timeout=settings.vod_analysis_sample_timeout_seconds,
    )
    return sorted(directory.glob("frame_*.jpg"))[:count]


class CoarseVisualAnalyzer:
    version = "opencv-yunet-coarse-v1"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._detector = None

    def _face_detector(self):
        if self._detector is None:
            from ..smart_vertical.face_detection import OpenCVFaceDetector

            self._detector = OpenCVFaceDetector(self.settings)
        return self._detector

    def analyze(self, paths: list[Path]) -> dict:
        frames = [frame for path in paths if (frame := cv2.imread(str(path))) is not None]
        if not frames:
            return {"sampled": False, "warning": "visual_sample_failed"}
        grays = [cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90)) for frame in frames]
        differences = [
            float(np.mean(cv2.absdiff(previous, current)) / 255.0)
            for previous, current in zip(grays, grays[1:], strict=False)
        ]
        detections = [self._face_detector().detect(frame, float(index)) for index, frame in enumerate(frames)]
        accepted = [
            item
            for frame_detections in detections
            for item in frame_detections
            if item.confidence >= self.settings.face_detector_score_threshold
        ]
        best = max(accepted, key=lambda item: item.area_ratio, default=None)
        position = None
        layout = "no_face"
        if best is not None:
            center_x = (best.region.x + best.region.width / 2) / best.frame_width
            center_y = (best.region.y + best.region.height / 2) / best.frame_height
            horizontal = "left" if center_x < 0.4 else "right" if center_x > 0.6 else "center"
            vertical = "top" if center_y < 0.4 else "bottom" if center_y > 0.6 else "center"
            position = f"{vertical}_{horizontal}"
            layout = "fullscreen_camera_hint" if best.area_ratio >= 0.08 else "facecam_overlay_hint"
        difference = float(np.mean(differences)) if differences else 0.0
        return {
            "sampled": True,
            "frame_count": len(frames),
            "scene_change_score": max(differences, default=0.0),
            "frame_difference": difference,
            "layout_hint": layout,
            "face_present": bool(accepted),
            "face_area_ratio": best.area_ratio if best is not None else 0.0,
            "facecam_position": position,
            "motion_score": difference,
            "warning": None,
        }
