import json
import logging
import math
import shutil
from pathlib import Path

import cv2

from ...config import Settings
from ...database import VodAnalysisStore
from .cache import SourceIdentity
from .fixtures import illojuan_fixture
from .layout_detection import (
    annotate_debug_frame,
    build_layout_timeline,
    classify_frame,
    extract_layout_frames,
    layout_cache_key,
    phase_timeline_from_layout,
    sample_timestamps,
)
from .metadata import inspect_analysis_metadata, stream_access_from_metadata
from .profiles import get_analysis_profile
from .schemas import (
    LayoutFrameSample,
    PhasedAnalysisResult,
    VodAnalysisResult,
)
from .timeline import (
    copy_timeline,
    load_layout_timeline,
    persist_layout_timeline,
    persist_phase_timeline,
)
from .visual_profiles import ProfileLayoutMatcher

logger = logging.getLogger(__name__)


class VodAnalysisAnalyzer:
    def __init__(self, store: VodAnalysisStore, settings: Settings):
        self.store = store
        self.settings = settings

    def process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None:
            return
        try:
            if job["fixture_mode"]:
                self._process_fixture(job)
            else:
                self._process_real(job)
        except Exception as exc:
            logger.exception("VOD analysis %s failed", job_id)
            self.store.update(
                job_id,
                status="failed",
                stage="failed",
                error_message=str(exc)[:1000],
            )

    def _update(
        self,
        job_id: str,
        stage: str,
        progress: int,
        *,
        completed: int = 0,
        total: int = 0,
        timestamp: float = 0,
    ) -> None:
        self.store.update(
            job_id,
            status="processing",
            stage=stage,
            progress=max(0, min(99, progress)),
            completed_windows=completed,
            total_windows=total,
            current_timestamp=timestamp,
            error_message=None,
        )

    def _process_fixture(self, job: dict) -> None:
        stages = (
            ("reading_metadata", 8),
            ("preparing_visual_stream", 18),
            ("sampling_layout_frames", 42),
            ("detecting_faces", 68),
            ("smoothing_layouts", 84),
            ("building_layout_timeline", 96),
        )
        for stage, progress in stages:
            self._update(job["id"], stage, progress)
        result = VodAnalysisResult.model_validate(
            illojuan_fixture(
                job["source_url"],
                job["source_platform"],
                job["source_vod_id"],
                job["pipeline_version"],
            )
        ).model_dump(mode="json")
        artifact_dir = self.settings.data_dir / "analysis" / job["id"]
        artifact_dir.mkdir(parents=True, exist_ok=True)
        layout_timeline, phase_timeline = self._write_fixture_artifacts(artifact_dir, result)
        visual_result = PhasedAnalysisResult(
            pipeline_version=self.settings.vod_analysis_phase_pipeline_version,
            fixture=True,
            vod={
                **result["vod"],
                "extractor": f"fixture:{job['source_platform']}",
                "original_url": result["vod"]["webpage_url"],
            },
            layout_timeline=layout_timeline,
            phase_timeline=phase_timeline,
            talking_blocks=phase_timeline.talking_blocks,
            selected_talking_blocks=phase_timeline.selected_talking_blocks,
            primary_talking_block_id=phase_timeline.primary_talking_block_id,
            phase_summary=phase_timeline.summary,
            warnings=phase_timeline.warnings,
        ).model_dump(mode="json")
        self.store.update(
            job["id"],
            status="completed",
            stage="completed",
            progress=100,
            warnings=visual_result["warnings"],
            result=visual_result,
            error_message=None,
        )

    def _process_real(self, job: dict) -> None:
        job_id = job["id"]
        identity = SourceIdentity(job["source_platform"], job["source_vod_id"])
        profile = get_analysis_profile(job["streamer_profile"])
        job_dir = self.settings.data_dir / "analysis" / job_id
        visual_key = layout_cache_key(identity.platform, identity.vod_id, profile.id, self.settings)
        cache_dir = self.settings.data_dir / "analysis" / "cache" / visual_key
        cache_phase_path = cache_dir / "phase_timeline.json"
        job_phase_path = job_dir / "phase_timeline.json"
        cache_layout_path = cache_dir / "layout_timeline.json"
        job_layout_path = job_dir / "layout_timeline.json"
        temp_root = job_dir / "tmp"
        job_dir.mkdir(parents=True, exist_ok=True)

        self._update(job_id, "reading_metadata", 2)
        metadata, _ = inspect_analysis_metadata(job["source_url"], identity, self.settings)
        (job_dir / "metadata.json").write_text(
            json.dumps(metadata.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        max_seconds = min(profile.max_initial_analysis_seconds, self.settings.vod_analysis_max_seconds)
        analyzed_duration = min(metadata.duration_seconds, max_seconds)
        layout_timeline = load_layout_timeline(cache_layout_path, visual_key)
        timestamps = sample_timestamps(analyzed_duration, self.settings.layout_sample_seconds)
        if layout_timeline is None or layout_timeline.completed_samples < len(timestamps):
            raw_samples = list(layout_timeline.raw_samples) if layout_timeline else []
            completed_samples = {item.index for item in raw_samples}
            layout_warnings = list(layout_timeline.warnings) if layout_timeline else []
            detector = None
            matcher = ProfileLayoutMatcher(
                self.settings.visual_layout_profile_path,
                self.settings.face_detector_score_threshold,
            )
            block_seconds = self.settings.vod_analysis_fetch_block_seconds
            block_count = max(1, math.ceil(analyzed_duration / block_seconds))
            for block_index in range(block_count):
                block_start = block_index * block_seconds
                block_end = min(analyzed_duration, block_start + block_seconds)
                block_items = [
                    (index, timestamp)
                    for index, timestamp in enumerate(timestamps)
                    if block_start <= timestamp < block_end and index not in completed_samples
                ]
                if not block_items:
                    continue
                self._update(
                    job_id,
                    "sampling_layout_frames",
                    15 + round(70 * len(completed_samples) / max(1, len(timestamps))),
                    completed=len(completed_samples),
                    total=len(timestamps),
                    timestamp=block_start,
                )
                block_dir = temp_root / f"layout_{block_index:04d}"
                try:
                    self._update(
                        job_id,
                        "preparing_visual_stream",
                        12 + round(70 * len(completed_samples) / max(1, len(timestamps))),
                        completed=len(completed_samples),
                        total=len(timestamps),
                        timestamp=block_start,
                    )
                    _, refreshed_metadata = inspect_analysis_metadata(
                        job["source_url"], identity, self.settings
                    )
                    access = stream_access_from_metadata(refreshed_metadata, video_height=720)
                    if not access.video_url:
                        raise RuntimeError("No video stream is available for OBS layout detection")
                    paths = extract_layout_frames(
                        access.video_url,
                        block_start,
                        block_end - block_start,
                        self.settings.layout_sample_seconds,
                        block_dir,
                        self.settings,
                        user_agent=access.user_agent,
                        referer=access.referer,
                    )
                    if detector is None:
                        from ..smart_vertical.face_detection import OpenCVFaceDetector

                        detector = OpenCVFaceDetector(self.settings)
                    self._update(
                        job_id,
                        "detecting_faces",
                        20 + round(70 * len(completed_samples) / max(1, len(timestamps))),
                        completed=len(completed_samples),
                        total=len(timestamps),
                        timestamp=block_start,
                    )
                    block_timestamps = [
                        timestamp for timestamp in timestamps if block_start <= timestamp < block_end
                    ]
                    for path, timestamp in zip(paths, block_timestamps, strict=False):
                        index = round(timestamp / self.settings.layout_sample_seconds)
                        if index in completed_samples:
                            continue
                        frame = cv2.imread(str(path))
                        sample, detections = classify_frame(
                            frame, timestamp, index, detector, matcher, self.settings
                        )
                        raw_samples.append(sample)
                        completed_samples.add(index)
                        if self.settings.validation_debug and frame is not None:
                            annotate_debug_frame(
                                job_dir / "frames_debug" / f"frame_{index:06d}.jpg",
                                frame,
                                sample,
                                detections,
                                self.settings,
                                matcher,
                            )
                    missing = [item for item in block_items if item[0] not in completed_samples]
                    for index, timestamp in missing:
                        sample, _ = classify_frame(None, timestamp, index, detector, matcher, self.settings)
                        raw_samples.append(sample)
                        completed_samples.add(index)
                        layout_warnings.append("layout_frame_missing")
                except Exception as exc:
                    logger.warning("Layout block %s failed: %s", block_index, exc)
                    layout_warnings.append("layout_sampling_block_failed")
                    for index, timestamp in block_items:
                        sample, _ = classify_frame(None, timestamp, index, detector, matcher, self.settings)
                        raw_samples.append(sample)
                        completed_samples.add(index)
                finally:
                    shutil.rmtree(block_dir, ignore_errors=True)
                layout_timeline = build_layout_timeline(
                    raw_samples,
                    analyzed_duration,
                    visual_key,
                    None,
                    self.settings,
                    layout_warnings,
                )
                persist_layout_timeline(cache_layout_path, layout_timeline)
                copy_timeline(cache_layout_path, job_layout_path)
                self.store.update(
                    job_id,
                    completed_windows=len(completed_samples),
                    total_windows=len(timestamps),
                    current_timestamp=block_end,
                )
        elif cache_layout_path.is_file():
            copy_timeline(cache_layout_path, job_layout_path)
        shutil.rmtree(temp_root, ignore_errors=True)
        assert layout_timeline is not None
        self._update(
            job_id,
            "smoothing_layouts",
            94,
            completed=layout_timeline.completed_samples,
            total=layout_timeline.total_samples,
            timestamp=analyzed_duration,
        )
        self._update(
            job_id,
            "building_layout_timeline",
            98,
            completed=layout_timeline.completed_samples,
            total=layout_timeline.total_samples,
            timestamp=analyzed_duration,
        )
        phase_timeline = phase_timeline_from_layout(layout_timeline, profile)
        persist_phase_timeline(cache_phase_path, phase_timeline)
        copy_timeline(cache_phase_path, job_phase_path)
        copy_timeline(cache_layout_path, job_layout_path)
        if self.settings.vod_analysis_debug:
            debug_artifacts = {
                "raw_phase_scores.json": phase_timeline.raw_windows,
                "smoothed_phase_windows.json": phase_timeline.smoothed_windows,
                "transitions.json": [
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "phase": segment.phase,
                        "transition_in": segment.transition_in,
                        "transition_out": segment.transition_out,
                    }
                    for segment in phase_timeline.segments
                ],
                "phase_debug_summary.json": {
                    "summary": phase_timeline.summary,
                    "warnings": phase_timeline.warnings,
                    "primary_talking_block_id": phase_timeline.primary_talking_block_id,
                },
            }
            for name, value in debug_artifacts.items():
                (job_dir / name).write_text(
                    json.dumps(
                        value.model_dump(mode="json") if hasattr(value, "model_dump") else value,
                        indent=2,
                        ensure_ascii=False,
                        default=lambda item: item.model_dump(mode="json"),
                    ),
                    encoding="utf-8",
                )
        combined_warnings = list(dict.fromkeys([*layout_timeline.warnings, *phase_timeline.warnings]))
        result = PhasedAnalysisResult(
            pipeline_version=self.settings.vod_analysis_phase_pipeline_version,
            vod=metadata,
            phase_timeline=phase_timeline,
            talking_blocks=phase_timeline.talking_blocks,
            selected_talking_blocks=phase_timeline.selected_talking_blocks,
            primary_talking_block_id=phase_timeline.primary_talking_block_id,
            phase_summary=phase_timeline.summary,
            layout_timeline=layout_timeline,
            warnings=combined_warnings,
        ).model_dump(mode="json")
        self.store.update(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            completed_windows=layout_timeline.completed_samples,
            total_windows=layout_timeline.total_samples,
            current_timestamp=analyzed_duration,
            warnings=combined_warnings,
            result=result,
            error_message=None,
        )

    def _write_fixture_artifacts(self, directory: Path, _result: dict):
        fixture_duration = 7200.0
        layout_samples = []
        for index, timestamp in enumerate(
            sample_timestamps(fixture_duration, self.settings.layout_sample_seconds)
        ):
            if timestamp < 1410:
                layout, layout_id, phase, confidence, area, position = (
                    "no_face",
                    "waiting_unmatched",
                    "waiting_or_music",
                    0.88,
                    0.0,
                    None,
                )
            elif timestamp < 5070:
                layout, layout_id, phase, confidence, area, position = (
                    "fullscreen_face",
                    "full_camera_room",
                    "talking",
                    0.90,
                    0.11,
                    "center",
                )
            else:
                layout, layout_id, phase, confidence, area, position = (
                    "small_facecam",
                    "gameplay_left",
                    "gameplay",
                    0.86,
                    0.025,
                    "top_left",
                )
            layout_samples.append(
                LayoutFrameSample(
                    index=index,
                    frame_timestamp=timestamp,
                    layout=layout,
                    layout_id=layout_id,
                    phase=phase,
                    confidence=confidence,
                    match_score=confidence,
                    second_best_score=0.2,
                    score_margin=confidence - 0.2,
                    face_area_ratio=area,
                    face_position=position,
                    reasons=[f"fixture_{layout}"],
                )
            )
        layout_timeline = build_layout_timeline(
            layout_samples,
            fixture_duration,
            "fixture-layout",
            None,
            self.settings,
        )
        phase_timeline = phase_timeline_from_layout(layout_timeline, get_analysis_profile("illojuan"))
        artifacts = {
            "phase_timeline.json": phase_timeline,
            "layout_timeline.json": layout_timeline,
        }
        for name, value in artifacts.items():
            (directory / name).write_text(
                json.dumps(
                    value.model_dump(mode="json") if hasattr(value, "model_dump") else value,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        return layout_timeline, phase_timeline
