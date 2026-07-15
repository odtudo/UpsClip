from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from itertools import groupby
from pathlib import Path

import cv2

from ...config import Settings
from ..process import run_command
from ..smart_vertical.face_detection import OpenCVFaceDetector
from .phase_detection import build_talking_blocks
from .profiles import AnalysisProfile
from .schemas import (
    ClassifiedPhaseWindow,
    LayoutFrameSample,
    LayoutSegment,
    LayoutTimeline,
    PhaseScores,
    PhaseSegment,
    PhaseSummary,
    PhaseTimeline,
)
from .visual_profiles import ProfileLayoutMatcher, visual_profile_fingerprint

LAYOUT_TO_PHASE = {
    "no_face": "waiting_or_music",
    "fullscreen_face": "talking",
    "small_facecam": "gameplay",
    "unknown": "unknown",
}


def layout_cache_key(platform: str, vod_id: str, profile_id: str, settings: Settings) -> str:
    payload = {
        "platform": platform,
        "vod_id": vod_id,
        "profile": profile_id,
        "pipeline": settings.vod_analysis_phase_pipeline_version,
        "sample_seconds": settings.layout_sample_seconds,
        "confirmation": settings.layout_transition_confirmation,
        "strategy": "profile_layout_match",
        "detector": "smart-vertical-opencv-yunet-v1",
        "matcher": "profile-layout-hist-dhash-edge-v2",
        "visual_profile_fingerprint": visual_profile_fingerprint(settings.visual_layout_profile_path),
        "face_detector_score_threshold": settings.face_detector_score_threshold,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def sample_timestamps(duration: float, interval: float) -> list[float]:
    if duration <= 0 or interval <= 0:
        return []
    count = max(1, int((duration - 1e-6) // interval) + 1)
    return [round(index * interval, 3) for index in range(count)]


def extract_layout_frames(
    stream_url: str,
    start: float,
    duration: float,
    interval: float,
    directory: Path,
    settings: Settings,
    *,
    user_agent: str | None = None,
    referer: str | None = None,
) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pattern = directory / "layout_%06d.jpg"
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
            f"fps=1/{interval:.6f},scale='min(1280,iw)':-2",
            "-q:v",
            "5",
            pattern,
        ],
        label="OBS layout frame sampling",
        timeout=max(settings.vod_analysis_sample_timeout_seconds, round(duration * 1.5)),
    )
    return sorted(directory.glob("layout_*.jpg"))


def classify_frame(
    frame,
    timestamp: float,
    index: int,
    detector: OpenCVFaceDetector,
    matcher: ProfileLayoutMatcher,
    settings: Settings,
) -> tuple[LayoutFrameSample, list]:
    detections = detector.detect(frame, timestamp) if frame is not None else []
    matched = matcher.match(frame, detections)
    layout = {
        "waiting_or_music": "no_face",
        "talking": "fullscreen_face",
        "gameplay": "small_facecam",
        "unknown": "unknown",
    }[matched.phase]
    confidence = matched.match_score
    if matched.phase == "waiting_or_music":
        confidence = max(0.0, 1.0 - matched.match_score)
    elif matched.phase == "unknown":
        confidence = max(0.0, matched.score_margin)
    return LayoutFrameSample(
        index=index,
        frame_timestamp=timestamp,
        layout=layout,
        layout_id=matched.layout_id,
        phase=matched.phase,
        confidence=confidence,
        match_score=matched.match_score,
        second_best_score=matched.second_best_score,
        score_margin=matched.score_margin,
        matched_reference=matched.matched_reference,
        face_area_ratio=matched.face_area_ratio,
        face_position=matched.face_position,
        face_box=matched.face_box,
        signals=matched.signals,
        background_region_scores=matched.background_region_scores,
        reasons=matched.reasons,
        warnings=matched.warnings,
    ), detections


def annotate_debug_frame(
    path: Path,
    frame,
    sample: LayoutFrameSample,
    detections: list,
    settings: Settings,
    matcher: ProfileLayoutMatcher,
) -> None:
    annotated = frame.copy()
    for detection in detections:
        accepted = detection.confidence >= settings.face_detector_score_threshold
        color = (0, 210, 0) if accepted else (0, 180, 255)
        box = detection.region
        cv2.rectangle(annotated, (box.x, box.y), (box.x + box.width, box.y + box.height), color, 2)
    definition = next((item for item in matcher.profile.layouts if item.id == sample.layout_id), None)
    if definition is not None:
        sx, sy = (
            frame.shape[1] / definition.source_resolution.width,
            frame.shape[0] / definition.source_resolution.height,
        )
        regions = [(definition.expected_face_region, (255, 120, 0))] + [
            (item, (255, 0, 220)) for item in definition.stable_background_regions
        ]
        for region, color in regions:
            x, y = round(region.x * sx), round(region.y * sy)
            w, h = round(region.width * sx), round(region.height * sy)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 1)
            cv2.putText(annotated, region.id, (x + 3, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)
    label = (
        f"{sample.layout_id} {sample.phase} score={sample.match_score:.2f} "
        f"second={sample.second_best_score:.2f} margin={sample.score_margin:.2f}"
    )
    cv2.putText(
        annotated,
        label,
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        3,
        cv2.LINE_AA,
    )
    reference = sample.matched_reference or "none"
    cv2.putText(annotated, f"ref={reference}", (12, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    y = 76
    for region, score in sorted(sample.background_region_scores.items()):
        cv2.putText(
            annotated, f"{region}={score:.2f}", (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1
        )
        y += 18
    cv2.putText(
        annotated,
        label,
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (20, 20, 20),
        1,
        cv2.LINE_AA,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), annotated)


def apply_hysteresis(samples: list[LayoutFrameSample], confirmation: int) -> list[LayoutFrameSample]:
    if not samples:
        return []
    phases = [sample.layout_id for sample in samples]
    current = phases[0]
    pending = None
    pending_start = 0
    pending_count = 0
    accepted = [current]
    for index in range(1, len(samples)):
        candidate = phases[index]
        if candidate == current:
            pending, pending_count = None, 0
            accepted.append(current)
            continue
        if candidate != pending:
            pending, pending_start, pending_count = candidate, index, 1
        else:
            pending_count += 1
        accepted.append(current)
        if pending_count >= confirmation:
            current = candidate
            for backfill in range(pending_start, index + 1):
                accepted[backfill] = current
            pending, pending_count = None, 0
    result = []
    representatives = {sample.layout_id: sample for sample in samples}
    for position, (sample, layout_id) in enumerate(zip(samples, accepted, strict=True)):
        reasons = list(sample.reasons)
        representative = representatives[layout_id]
        if layout_id != sample.layout_id:
            reasons.append("layout_hysteresis_suppressed_transition")
        elif position > 0 and layout_id != accepted[position - 1] and confirmation > 1:
            reasons.append("layout_transition_confirmed")
        result.append(
            sample.model_copy(
                update={
                    "layout": representative.layout,
                    "layout_id": layout_id,
                    "phase": representative.phase,
                    "reasons": reasons,
                }
            )
        )
    return result


def merge_layout_segments(
    samples: list[LayoutFrameSample], duration: float, interval: float
) -> list[LayoutSegment]:
    segments: list[LayoutSegment] = []
    for _layout_id, grouped in groupby(samples, key=lambda item: item.layout_id):
        group = list(grouped)
        first, last = group[0], group[-1]
        end = min(duration, last.frame_timestamp + interval)
        if end <= first.frame_timestamp:
            continue
        segments.append(
            LayoutSegment(
                start=first.frame_timestamp,
                end=end,
                layout=first.layout,
                layout_id=first.layout_id,
                phase=first.phase,
                confidence=statistics.median(item.confidence for item in group),
                match_score=statistics.median(item.match_score for item in group),
                second_best_score=statistics.median(item.second_best_score for item in group),
                score_margin=statistics.median(item.score_margin for item in group),
                sample_count=len(group),
                reasons=list(dict.fromkeys(reason for item in group for reason in item.reasons)),
                warnings=list(dict.fromkeys(warning for item in group for warning in item.warnings)),
            )
        )
    return segments


def build_layout_timeline(
    raw_samples: list[LayoutFrameSample],
    duration: float,
    cache_key: str,
    source_coarse_cache_key: str | None,
    settings: Settings,
    warnings: list[str] | None = None,
) -> LayoutTimeline:
    ordered = sorted(raw_samples, key=lambda item: item.index)
    smoothed = apply_hysteresis(ordered, settings.layout_transition_confirmation)
    segments = merge_layout_segments(smoothed, duration, settings.layout_sample_seconds)
    timeline_warnings = list(warnings or [])
    if ordered and all(item.layout == "unknown" for item in ordered):
        timeline_warnings.append("layout_no_determinable_samples")
    total = len(sample_timestamps(duration, settings.layout_sample_seconds))
    return LayoutTimeline(
        pipeline_version=settings.vod_analysis_phase_pipeline_version,
        cache_key=cache_key,
        source_coarse_cache_key=source_coarse_cache_key,
        sample_seconds=settings.layout_sample_seconds,
        transition_confirmation=settings.layout_transition_confirmation,
        analyzed_duration_seconds=duration,
        completed_samples=len(ordered),
        total_samples=total,
        raw_samples=ordered,
        smoothed_samples=smoothed,
        segments=segments,
        warnings=list(dict.fromkeys(timeline_warnings)),
    )


def phase_timeline_from_layout(
    layout: LayoutTimeline,
    profile: AnalysisProfile,
) -> PhaseTimeline:
    raw_by_index = {item.index: item for item in layout.raw_samples}

    def converted(sample: LayoutFrameSample) -> ClassifiedPhaseWindow:
        raw = raw_by_index[sample.index]
        raw_scores = {name: 0.0 for name in ("waiting_or_music", "talking", "gameplay", "unknown")}
        raw_scores[raw.phase] = raw.confidence
        return ClassifiedPhaseWindow(
            index=sample.index,
            start=sample.frame_timestamp,
            end=min(layout.analyzed_duration_seconds, sample.frame_timestamp + layout.sample_seconds),
            raw_phase=raw.phase,
            raw_confidence=raw.confidence,
            phase=sample.phase,
            confidence=sample.confidence,
            phase_scores=PhaseScores(**raw_scores),
            reasons=sample.reasons,
            smoothing_reasons=([] if sample.layout == raw.layout else ["layout_hysteresis"]),
            warnings=sample.warnings,
        )

    raw_windows = [
        converted(
            item.model_copy(
                update={"layout": raw_by_index[item.index].layout, "phase": raw_by_index[item.index].phase}
            )
        )
        for item in layout.raw_samples
    ]
    smoothed_windows = [converted(item) for item in layout.smoothed_samples]
    segments = [
        PhaseSegment(
            start=item.start,
            end=item.end,
            phase=item.phase,
            confidence=item.confidence,
            window_count=item.sample_count,
            reasons=item.reasons,
            warnings=item.warnings,
        )
        for item in layout.segments
    ]
    for index, segment in enumerate(segments):
        segment.transition_in = None if index == 0 else f"{segments[index - 1].phase}_to_{segment.phase}"
        segment.transition_out = (
            None if index == len(segments) - 1 else f"{segment.phase}_to_{segments[index + 1].phase}"
        )
    blocks, selected, primary, warnings = build_talking_blocks(segments, profile)
    durations = Counter()
    for segment in segments:
        durations[segment.phase] += segment.end - segment.start
    phase_key = hashlib.sha256(f"{layout.cache_key}:{layout.pipeline_version}".encode()).hexdigest()
    return PhaseTimeline(
        pipeline_version=layout.pipeline_version,
        phase_detection_strategy=layout.phase_detection_strategy,
        requires_coarse_timeline=False,
        source_coarse_pipeline_version=None,
        source_coarse_cache_key=layout.source_coarse_cache_key,
        phase_cache_key=phase_key,
        window_seconds=round(layout.sample_seconds),
        raw_windows=raw_windows,
        smoothed_windows=smoothed_windows,
        segments=segments,
        talking_blocks=blocks,
        selected_talking_blocks=selected,
        primary_talking_block_id=primary,
        warnings=[*layout.warnings, *warnings],
        summary=PhaseSummary(
            waiting_seconds=durations["waiting_or_music"],
            talking_seconds=durations["talking"],
            gameplay_seconds=durations["gameplay"],
            unknown_seconds=durations["unknown"],
        ),
    )
