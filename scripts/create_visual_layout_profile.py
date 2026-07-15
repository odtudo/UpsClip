#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from apps.api.app.services.vod_analysis.visual_profiles import (
    AreaRange,
    ProfileRegion,
    Resolution,
    VisualLayoutDefinition,
    VisualLayoutProfile,
    dump_profile,
    load_visual_profile,
)


def region(value: str, *, default_id: str) -> ProfileRegion:
    parts = value.split(":")
    name, coordinates = (parts[0], parts[1]) if len(parts) == 2 else (default_id, parts[0])
    values = [int(item) for item in coordinates.split(",")]
    if len(values) != 4:
        raise argparse.ArgumentTypeError("regions use [id:]x,y,width,height")
    return ProfileRegion(id=name, x=values[0], y=values[1], width=values[2], height=values[3])


def main() -> int:
    parser = argparse.ArgumentParser(description="Add a measured reference layout to a visual profile")
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--layout-id", required=True)
    parser.add_argument("--phase", required=True, choices=("talking", "gameplay"))
    parser.add_argument("--face-region", required=True)
    parser.add_argument("--face-area", default="0.01,0.10", help="minimum,maximum ratio")
    parser.add_argument("--position", default="center")
    parser.add_argument("--webcam-region")
    parser.add_argument("--background-region", action="append", default=[])
    parser.add_argument("--threshold", type=float, default=0.70)
    args = parser.parse_args()

    profile_path, reference_path = args.profile.resolve(), args.reference.resolve()
    image = cv2.imread(str(reference_path))
    if image is None:
        parser.error("reference is missing or cannot be decoded")
    try:
        relative_reference = reference_path.relative_to(profile_path.parent)
    except ValueError:
        parser.error("reference must live below the profile directory")
    if profile_path.exists():
        profile = load_visual_profile(profile_path)
    else:
        profile = VisualLayoutProfile(id=profile_path.stem, display_name=profile_path.stem, layouts=[])
    if any(item.id == args.layout_id for item in profile.layouts):
        parser.error("layout id already exists; edit the JSON to add another reference")
    minimum, maximum = (float(item) for item in args.face_area.split(","))
    profile.layouts.append(
        VisualLayoutDefinition(
            id=args.layout_id,
            phase=args.phase,
            source_resolution=Resolution(width=image.shape[1], height=image.shape[0]),
            expected_face_region=region(args.face_region, default_id="expected_face"),
            expected_webcam_region=(
                region(args.webcam_region, default_id="expected_webcam") if args.webcam_region else None
            ),
            expected_face_area_ratio=AreaRange(min=minimum, max=maximum),
            expected_position=args.position,
            stable_background_regions=[
                region(item, default_id=f"background_{index}")
                for index, item in enumerate(args.background_region)
            ],
            reference_images=[str(relative_reference)],
            weights={
                "face_position": 0.15,
                "face_size": 0.10,
                "background_similarity": 0.30,
                "reference_similarity": 0.35,
                "temporal_stability": 0.10,
            },
            minimum_match_score=args.threshold,
        )
    )
    profile.version += 1
    dump_profile(profile_path, profile)
    load_visual_profile(profile_path)
    print(f"Saved validated layout '{args.layout_id}' in {profile_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
