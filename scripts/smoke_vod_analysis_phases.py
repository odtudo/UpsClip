#!/usr/bin/env python3
"""Run Phase 3 from a fixture or an existing coarse timeline. Never accesses media."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.app.config import get_settings
from apps.api.app.services.vod_analysis.fixtures import phase_detection_fixture
from apps.api.app.services.vod_analysis.phase_detection import build_phase_timeline
from apps.api.app.services.vod_analysis.profiles import ILLOJUAN
from apps.api.app.services.vod_analysis.schemas import CoarseTimeline, CoarseVodMetadata
from apps.api.app.services.vod_analysis.timeline import persist_phase_timeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coarse_timeline", nargs="?", type=Path, help="Existing coarse_timeline.json")
    parser.add_argument("--metadata", type=Path, help="Optional matching metadata.json")
    parser.add_argument("--output", type=Path, default=Path("/tmp/phase_timeline.json"))
    args = parser.parse_args()
    settings = get_settings()
    coarse = (
        CoarseTimeline.model_validate_json(args.coarse_timeline.read_text(encoding="utf-8"))
        if args.coarse_timeline
        else CoarseTimeline.model_validate(phase_detection_fixture())
    )
    if args.metadata:
        metadata = CoarseVodMetadata.model_validate_json(args.metadata.read_text(encoding="utf-8"))
    else:
        metadata = CoarseVodMetadata(
            platform="twitch",
            extractor="fixture",
            vod_id="phase-smoke",
            title="Phase 3 smoke",
            uploader="IlloJuan",
            duration_seconds=coarse.analyzed_duration_seconds,
            original_url="https://www.twitch.tv/videos/123456789",
        )
    timeline = build_phase_timeline(coarse, metadata, ILLOJUAN, settings.vod_analysis_phase_pipeline_version)
    persist_phase_timeline(args.output, timeline)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "segments": [
                    {
                        "phase": item.phase,
                        "start": item.start,
                        "end": item.end,
                        "confidence": round(item.confidence, 3),
                    }
                    for item in timeline.segments
                ],
                "talking_blocks": [item.model_dump(mode="json") for item in timeline.talking_blocks],
                "primary_talking_block_id": timeline.primary_talking_block_id,
                "selected_talking_blocks": [
                    item.model_dump(mode="json") for item in timeline.selected_talking_blocks
                ],
                "summary": timeline.summary.model_dump(mode="json"),
                "warnings": timeline.warnings,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
