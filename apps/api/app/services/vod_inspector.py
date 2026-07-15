from __future__ import annotations

import json
import statistics
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import cv2
import numpy as np

from ..config import Settings
from .vod_analysis.layout_detection import phase_timeline_from_layout
from .vod_analysis.phase_detection import build_phase_timeline
from .vod_analysis.profiles import get_analysis_profile
from .vod_analysis.schemas import (
    CoarseTimeline,
    CoarseVodMetadata,
    InspectorSegment,
    LayoutTimeline,
    PhaseTimeline,
    ValidationComparison,
    ValidationMetrics,
    ValidationNotes,
    VodInspectorResponse,
)
from .vod_analysis.timeline import persist_phase_timeline
from .vod_analysis.visual_profiles import load_visual_profile, visual_profile_fingerprint

PHASE_COLORS = {
    "waiting_or_music": (64, 180, 245),
    "talking": (94, 178, 34),
    "gameplay": (211, 82, 124),
    "unknown": (130, 130, 130),
}
EXPORT_FILES = (
    "metadata.json",
    "coarse_timeline.json",
    "phase_timeline.json",
    "layout_timeline.json",
    "timeline.png",
    "summary.md",
    "validation_report.md",
    "raw_phase_scores.json",
    "smoothed_windows.json",
    "transition_graph.json",
)


def timestamp_url(source_url: str, seconds: float) -> str:
    value = max(0, round(seconds))
    parsed = urlparse(source_url)
    host = (parsed.hostname or "").lower()
    if host.endswith("twitch.tv"):
        hours, remainder = divmod(value, 3600)
        minutes, secs = divmod(remainder, 60)
        stamp = f"{hours}h{minutes}m{secs}s"
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["t"] = stamp
        return urlunparse(parsed._replace(query=urlencode(query)))
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["t"] = str(value)
        return urlunparse(parsed._replace(query=urlencode(query)))
    raise ValueError("Unsupported VOD platform")


def format_timestamp(seconds: float) -> str:
    value = max(0, round(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def compare_notes(timeline: PhaseTimeline, notes: ValidationNotes) -> list[ValidationComparison]:
    primary = next(
        (item for item in timeline.talking_blocks if item.id == timeline.primary_talking_block_id),
        timeline.talking_blocks[0] if timeline.talking_blocks else None,
    )
    gameplay = [item for item in timeline.segments if item.phase == "gameplay"]
    talking = timeline.talking_blocks
    detectors = {
        "talking_start": primary.start_seconds if primary else None,
        "talking_end": primary.end_seconds if primary else None,
        "gameplay_start": gameplay[0].start if gameplay else None,
        "gameplay_end": gameplay[0].end if gameplay else None,
        "talking_block_2_start": talking[1].start_seconds if len(talking) > 1 else None,
        "talking_block_2_end": talking[1].end_seconds if len(talking) > 1 else None,
        "talking_block_3_start": talking[2].start_seconds if len(talking) > 2 else None,
        "talking_block_3_end": talking[2].end_seconds if len(talking) > 2 else None,
    }
    comparisons = []
    for name, actual in notes.model_dump().items():
        if actual is None:
            continue
        detector = detectors[name]
        error = None if detector is None else detector - actual
        comparisons.append(
            ValidationComparison(
                transition=name,
                detector_seconds=detector,
                actual_seconds=actual,
                error_seconds=error,
                absolute_error_seconds=None if error is None else abs(error),
            )
        )
    return comparisons


def calculate_metrics(
    timeline: PhaseTimeline,
    notes: ValidationNotes,
    comparisons: list[ValidationComparison],
) -> ValidationMetrics:
    errors = [item.absolute_error_seconds for item in comparisons if item.absolute_error_seconds is not None]
    detected_talking = len(timeline.talking_blocks)
    detected_gameplay = sum(item.phase == "gameplay" for item in timeline.segments)
    manual_talking = sum(
        getattr(notes, field) is not None
        for field in ("talking_start", "talking_block_2_start", "talking_block_3_start")
    )
    manual_gameplay = int(notes.gameplay_start is not None)
    false_detections = 0
    if manual_talking:
        false_detections += max(0, detected_talking - manual_talking)
    if manual_gameplay:
        false_detections += max(0, detected_gameplay - manual_gameplay)
    total_duration = sum(item.end - item.start for item in timeline.segments)
    mean_confidence = (
        sum((item.end - item.start) * item.confidence for item in timeline.segments) / total_duration
        if total_duration
        else 0
    )
    signed_by_transition = {
        item.transition: item.error_seconds for item in comparisons if item.error_seconds is not None
    }
    return ValidationMetrics(
        mean_absolute_error_seconds=statistics.fmean(errors) if errors else None,
        maximum_absolute_error_seconds=max(errors) if errors else None,
        mean_error_by_transition=signed_by_transition,
        detected_phase_count=len(timeline.segments),
        omitted_phase_count=sum(item.detector_seconds is None for item in comparisons),
        false_detection_count=false_detections,
        mean_confidence=mean_confidence,
    )


def load_notes(directory: Path) -> ValidationNotes:
    try:
        return ValidationNotes.model_validate_json(
            (directory / "validation_notes.json").read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, ValueError):
        return ValidationNotes()


def save_notes(directory: Path, notes: ValidationNotes) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / "validation_notes.tmp"
    temporary.write_text(notes.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(directory / "validation_notes.json")


def _metadata_from_job(job: dict) -> CoarseVodMetadata:
    value = (job.get("result") or {}).get("vod") or {}
    return CoarseVodMetadata(
        platform=value.get("platform", job["source_platform"]),
        extractor=value.get("extractor", "fixture"),
        vod_id=value.get("vod_id", job["source_vod_id"]),
        title=value.get("title", "VOD Inspector"),
        uploader=value.get("uploader"),
        channel=value.get("channel"),
        duration_seconds=value.get("duration_seconds", 0),
        chapters=value.get("chapters", []),
        original_url=value.get("original_url", value.get("webpage_url", job["source_url"])),
        availability=value.get("availability"),
        audio_formats=value.get("audio_formats", []),
        video_formats=value.get("video_formats", []),
    )


def _load_artifacts(
    job: dict, settings: Settings
) -> tuple[Path, CoarseVodMetadata, LayoutTimeline | None, PhaseTimeline, CoarseTimeline | None]:
    directory = settings.data_dir / "analysis" / job["id"]
    result = job.get("result") or {}
    metadata_path = directory / "metadata.json"
    try:
        metadata = CoarseVodMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        metadata = _metadata_from_job(job)
        metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    layout_path = directory / "layout_timeline.json"
    try:
        layout = LayoutTimeline.model_validate_json(layout_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        layout = None
        if result.get("layout_timeline"):
            layout = LayoutTimeline.model_validate(result["layout_timeline"])
            layout_path.write_text(layout.model_dump_json(indent=2), encoding="utf-8")
    coarse = None
    try:
        coarse = CoarseTimeline.model_validate_json(
            (directory / "coarse_timeline.json").read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, ValueError):
        pass
    phase_path = directory / "phase_timeline.json"
    try:
        phase = PhaseTimeline.model_validate_json(phase_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        if result.get("phase_timeline"):
            phase = PhaseTimeline.model_validate(result["phase_timeline"])
        elif layout is not None:
            phase = phase_timeline_from_layout(layout, get_analysis_profile(job["streamer_profile"]))
        elif coarse is not None:
            phase = build_phase_timeline(
                coarse,
                metadata,
                get_analysis_profile(job["streamer_profile"]),
                settings.vod_analysis_phase_pipeline_version,
            )
        else:
            raise RuntimeError("No visual or legacy phase timeline is available") from None
        persist_phase_timeline(phase_path, phase)
    if (
        layout is not None
        and job.get("phase_detection_strategy") in {"visual_layout", "profile_layout_match"}
        and phase.phase_detection_strategy != job.get("phase_detection_strategy")
    ):
        phase = phase_timeline_from_layout(layout, get_analysis_profile(job["streamer_profile"]))
        persist_phase_timeline(phase_path, phase)
    return directory, metadata, layout, phase, coarse


def render_timeline_png(path: Path, timeline: PhaseTimeline) -> None:
    width = 1600
    row_height = 42
    height = 130 + max(1, len(timeline.segments)) * row_height
    image = np.full((height, width, 3), 248, dtype=np.uint8)
    total = max((item.end for item in timeline.segments), default=1)
    left, right, top, bar_height = 80, width - 50, 45, 42
    cv2.putText(
        image,
        "VOD Inspector - detected phase timeline",
        (left, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (25, 25, 25),
        2,
    )
    for segment in timeline.segments:
        x1 = left + round((right - left) * segment.start / total)
        x2 = left + round((right - left) * segment.end / total)
        cv2.rectangle(image, (x1, top), (max(x1 + 2, x2), top + bar_height), PHASE_COLORS[segment.phase], -1)
    for index, segment in enumerate(timeline.segments):
        y = 115 + index * row_height
        label = (
            f"{format_timestamp(segment.start)}-{format_timestamp(segment.end)}  "
            f"{segment.phase}  confidence={segment.confidence:.3f}"
        )
        cv2.putText(image, label, (left, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (35, 35, 35), 1, cv2.LINE_AA)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError("Could not write inspector timeline PNG")


def _analysis_seconds(job: dict) -> float:
    try:
        start = datetime.fromisoformat(job["created_at"])
        end = datetime.fromisoformat(job["updated_at"])
        return max(0, (end - start).total_seconds())
    except (KeyError, TypeError, ValueError):
        return 0


def build_report(
    job: dict,
    settings: Settings,
    metadata: CoarseVodMetadata,
    layout: LayoutTimeline | None,
    phase: PhaseTimeline,
    notes: ValidationNotes,
    comparisons: list[ValidationComparison],
    metrics: ValidationMetrics,
) -> str:
    analyzed_duration = (
        layout.analyzed_duration_seconds if layout else sum(item.end - item.start for item in phase.segments)
    )
    visual_profile = load_visual_profile(settings.visual_layout_profile_path)
    visual_thresholds = {
        "layout_sample_seconds": settings.layout_sample_seconds,
        "layout_transition_confirmation": settings.layout_transition_confirmation,
        "face_detector_score_threshold": settings.face_detector_score_threshold,
        "profile_id": visual_profile.id,
        "profile_version": visual_profile.version,
        "profile_fingerprint": visual_profile_fingerprint(settings.visual_layout_profile_path),
        "ambiguity_margin": visual_profile.ambiguity_margin,
        "minimum_frame_sharpness": visual_profile.minimum_frame_sharpness,
        "layouts": {
            item.id: {
                "enabled": item.enabled,
                "phase": item.phase,
                "minimum_match_score": item.minimum_match_score,
                "weights": item.weights,
            }
            for item in visual_profile.layouts
        },
        "detector": "Smart Vertical OpenCV YuNet",
        "matcher": "HSV histogram + difference hash + edge map",
    }
    lines = [
        "# VOD Inspector validation report",
        "",
        f"- Pipeline version: `{phase.pipeline_version}`",
        f"- Detection strategy: `{phase.phase_detection_strategy}`",
        f"- Requires coarse timeline: `{phase.requires_coarse_timeline}`",
        f"- Source: {metadata.title}",
        f"- Layout samples: {layout.completed_samples if layout else 'legacy unavailable'}",
        f"- Analyzed duration: {format_timestamp(analyzed_duration)}",
        f"- Waiting detected: {format_timestamp(phase.summary.waiting_seconds)}",
        f"- Talking detected: {format_timestamp(phase.summary.talking_seconds)}",
        f"- Gameplay detected: {format_timestamp(phase.summary.gameplay_seconds)}",
        f"- Unknown: {format_timestamp(phase.summary.unknown_seconds)}",
        f"- Talking blocks: {len(phase.talking_blocks)}",
        f"- Primary block: {phase.primary_talking_block_id or 'none'}",
        f"- Warnings: {', '.join(phase.warnings) or 'none'}",
        f"- Mean confidence: {metrics.mean_confidence:.3f}",
        f"- Analysis time: {_analysis_seconds(job):.2f} seconds",
        "",
        "## Thresholds used",
        "",
        "```json",
        json.dumps(visual_thresholds, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Detected segments",
        "",
    ]
    for segment in phase.segments:
        lines.append(
            f"- {format_timestamp(segment.start)}–{format_timestamp(segment.end)} "
            f"{segment.phase}, confidence {segment.confidence:.3f}; reasons: "
            f"{', '.join(segment.reasons) or 'none'}; warnings: {', '.join(segment.warnings) or 'none'}"
        )
    if layout is not None:
        lines.extend(["", "## Matched OBS layouts", ""])
        for segment in layout.segments:
            lines.append(
                f"- {format_timestamp(segment.start)}–{format_timestamp(segment.end)} "
                f"`{segment.layout_id}`: match {segment.match_score:.3f}, "
                f"second {segment.second_best_score:.3f}, margin {segment.score_margin:.3f}"
            )
    lines.extend(["", "## Manual comparison", ""])
    if not comparisons:
        lines.append("No validation notes supplied.")
    for item in comparisons:
        detected = "missing" if item.detector_seconds is None else format_timestamp(item.detector_seconds)
        error = "n/a" if item.error_seconds is None else f"{item.error_seconds:+.1f} seconds"
        lines.append(
            f"- {item.transition}: detector {detected}; actual "
            f"{format_timestamp(item.actual_seconds)}; error {error}"
        )
    lines.extend(
        [
            "",
            "## Metrics",
            "",
            f"- Mean absolute error: {metrics.mean_absolute_error_seconds}",
            f"- Maximum absolute error: {metrics.maximum_absolute_error_seconds}",
            f"- Detected phases: {metrics.detected_phase_count}",
            f"- Omitted phases: {metrics.omitted_phase_count}",
            f"- False detections: {metrics.false_detection_count}",
            "",
            "## Validation notes JSON",
            "",
            "```json",
            notes.model_dump_json(indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def prepare_inspector(job: dict, settings: Settings) -> VodInspectorResponse:
    if job["status"] != "completed":
        return VodInspectorResponse(
            job_id=job["id"],
            source_url=job["source_url"],
            streamer_profile=job["streamer_profile"],
            status=job["status"],
            stage=job["stage"],
            progress=job["progress"],
            error_message=job.get("error_message"),
            cached=job["cached"],
            phase_detection_strategy=job.get("phase_detection_strategy", "legacy_heuristic"),
            requires_coarse_timeline=job.get("requires_coarse_timeline", True),
        )
    directory, metadata, layout, phase, _coarse = _load_artifacts(job, settings)
    notes = load_notes(directory)
    comparisons = compare_notes(phase, notes)
    metrics = calculate_metrics(phase, notes, comparisons)
    layout_by_boundary = (
        {(round(item.start, 3), round(item.end, 3)): item for item in layout.segments}
        if layout is not None
        else {}
    )
    segments = [
        InspectorSegment(
            start=item.start,
            end=item.end,
            phase=item.phase,
            confidence=item.confidence,
            layout_id=(
                matched.layout_id
                if (matched := layout_by_boundary.get((round(item.start, 3), round(item.end, 3))))
                else None
            ),
            match_score=matched.match_score if matched else None,
            second_best_score=matched.second_best_score if matched else None,
            score_margin=matched.score_margin if matched else None,
            reasons=item.reasons,
            warnings=item.warnings,
            open_url=timestamp_url(job["source_url"], item.start),
        )
        for item in phase.segments
    ]
    return VodInspectorResponse(
        job_id=job["id"],
        source_url=job["source_url"],
        streamer_profile=job["streamer_profile"],
        status=job["status"],
        stage=job["stage"],
        progress=job["progress"],
        cached=job["cached"],
        phase_detection_strategy=job.get("phase_detection_strategy", "legacy_heuristic"),
        requires_coarse_timeline=job.get("requires_coarse_timeline", True),
        metadata=metadata,
        phase_timeline=phase,
        segments=segments,
        validation_notes=notes,
        comparisons=comparisons,
        metrics=metrics,
        export_url=f"/vod-inspector/{job['id']}/export",
    )


def export_report(job: dict, settings: Settings) -> Path:
    directory, metadata, layout, phase, _coarse = _load_artifacts(job, settings)
    if job.get("phase_detection_strategy") in {"visual_layout", "profile_layout_match"} and layout is None:
        raise RuntimeError("Layout timeline is missing for this completed visual analysis")
    notes = load_notes(directory)
    comparisons = compare_notes(phase, notes)
    metrics = calculate_metrics(phase, notes, comparisons)
    render_timeline_png(directory / "timeline.png", phase)
    report = build_report(job, settings, metadata, layout, phase, notes, comparisons, metrics)
    (directory / "validation_report.md").write_text(report, encoding="utf-8")
    summary = "\n".join(
        [
            "# VOD Inspector summary",
            "",
            f"Segments: {len(phase.segments)}",
            f"Talking blocks: {len(phase.talking_blocks)}",
            f"Primary: {phase.primary_talking_block_id or 'none'}",
            f"Mean confidence: {metrics.mean_confidence:.3f}",
            f"Warnings: {', '.join(phase.warnings) or 'none'}",
            "",
        ]
    )
    (directory / "summary.md").write_text(summary, encoding="utf-8")
    if settings.validation_debug:
        (directory / "raw_phase_scores.json").write_text(
            json.dumps([item.model_dump(mode="json") for item in phase.raw_windows], indent=2),
            encoding="utf-8",
        )
        (directory / "smoothed_windows.json").write_text(
            json.dumps([item.model_dump(mode="json") for item in phase.smoothed_windows], indent=2),
            encoding="utf-8",
        )
        graph = [
            {
                "phase": item.phase,
                "start": item.start,
                "end": item.end,
                "transition_in": item.transition_in,
                "transition_out": item.transition_out,
            }
            for item in phase.segments
        ]
        (directory / "transition_graph.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    destination = directory / "vod_inspector_validation.zip"
    temporary = directory / "vod_inspector_validation.tmp"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in EXPORT_FILES:
            candidate = directory / name
            if candidate.is_file():
                archive.write(candidate, arcname=name)
    temporary.replace(destination)
    return destination
