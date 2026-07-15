#!/usr/bin/env python3
"""Re-analyze an existing edited job without downloading Twitch media again."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.app.config import Settings  # noqa: E402
from apps.api.app.database import JobStore, safe_data_path  # noqa: E402
from apps.api.app.services.media import probe_media  # noqa: E402
from apps.api.app.services.process import run_command  # noqa: E402
from apps.api.app.services.smart_vertical.planner import build_composition_plan  # noqa: E402
from apps.api.app.services.smart_vertical.renderer import render_composition_plan  # noqa: E402
from apps.api.app.services.subtitles import burn_subtitles  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id")
    parser.add_argument("--uploader", help="Uploader reported by yt-dlp (for profile resolution)")
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=None,
        help="Verification output directory (default: data/smoke_tests/real_<job id>)",
    )
    return parser.parse_args()


def extract_frame(source: Path, timestamp: float, destination: Path, settings: Settings) -> None:
    run_command(
        [
            settings.ffmpeg_path,
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            source,
            "-frames:v",
            "1",
            destination,
        ],
        label="Verification frame extraction",
        timeout=120,
    )


def main() -> int:
    args = parse_args()
    settings = Settings()
    settings.smart_layout_debug = True
    store = JobStore(settings)
    store.initialize()
    job = store.get(args.job_id)
    if not job:
        raise SystemExit(f"Job not found: {args.job_id}")
    work = safe_data_path(settings.data_dir / "work" / args.job_id, settings.data_dir)
    source = safe_data_path(work / "edited_timeline.mp4", settings.data_dir)
    if not source.is_file():
        raise SystemExit(f"Edited timeline is missing: {source.name}")
    uploader = args.uploader
    if not uploader:
        raise SystemExit("Pass --uploader with the exact uploader value previously reported by yt-dlp.")

    artifacts = args.artifacts or settings.data_dir / "smoke_tests" / f"real_{args.job_id}"
    artifacts = safe_data_path(artifacts, settings.data_dir)
    artifacts.mkdir(parents=True, exist_ok=True)
    plan_path = work / "composition_plan.json"
    original_plan = work / "composition_plan_before_yunet.json"
    if plan_path.is_file() and not original_plan.exists():
        shutil.copy2(plan_path, original_plan)

    plan = build_composition_plan(
        source,
        plan_path,
        requested_profile=job.get("streamer_profile") or "auto",
        uploader=uploader,
        settings=settings,
    )
    composed = work / "vertical_composed_yunet.mp4"
    metrics = render_composition_plan(source, composed, plan, work, settings)
    plan["render_metrics"] = metrics
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    final = artifacts / "final.mp4"
    subtitles = settings.data_dir / "subtitles" / f"{args.job_id}.ass"
    if job.get("generate_subtitles") and subtitles.is_file():
        burn_subtitles(composed, subtitles, final, settings)
    else:
        shutil.copy2(composed, final)

    final_probe = probe_media(final, settings)
    video = next(item for item in final_probe["streams"] if item.get("codec_type") == "video")
    if (int(video["width"]), int(video["height"])) != (
        settings.vertical_output_width,
        settings.vertical_output_height,
    ):
        raise SystemExit("Reprocessed output has an unexpected resolution")

    representative = min(30.0, float(plan["source"]["duration"]) / 3)
    extract_frame(source, representative, artifacts / "source_frame.png", settings)
    extract_frame(final, representative, artifacts / "final_frame.png", settings)
    debug_dir = work / "smart_vertical_debug"
    debug_frames = sorted(debug_dir.glob("frame_*_final.jpg"))
    if debug_frames:
        shutil.copy2(debug_frames[len(debug_frames) // 3], artifacts / "detections.png")
    shutil.copy2(plan_path, artifacts / "composition_plan.json")

    rendered = settings.data_dir / "rendered" / f"{args.job_id}.mp4"
    original_render = work / "rendered_before_yunet.mp4"
    if rendered.is_file() and not original_render.exists():
        shutil.copy2(rendered, original_render)
    shutil.copy2(final, rendered)
    store.update(
        args.job_id,
        composition_plan_path=str(plan_path),
        resolved_streamer_profile=plan.get("profile_resolved"),
        layout_warnings=plan["warnings"],
        layout_summary=plan["summary"],
        rendered_path=str(rendered),
        rendered_duration=float(final_probe["format"]["duration"]),
        rendered_size=rendered.stat().st_size,
        status="ready",
        progress=100,
        current_step="Ready for preview (YuNet reprocessed)",
        error_message=None,
    )
    print(json.dumps({"plan": str(plan_path), "final": str(final), "artifacts": str(artifacts)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
