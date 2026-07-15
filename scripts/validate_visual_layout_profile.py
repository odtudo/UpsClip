#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from apps.api.app.services.vod_analysis.visual_profiles import (
    load_visual_profile,
    visual_profile_fingerprint,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a local OBS visual layout profile")
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    profile = load_visual_profile(args.profile.resolve())
    print(f"Profile: {profile.id} v{profile.version}")
    print(f"Fingerprint: {visual_profile_fingerprint(args.profile.resolve())}")
    for layout in profile.layouts:
        state = "enabled" if layout.enabled else "disabled"
        print(
            f"- {layout.id}: {layout.phase}, {state}, "
            f"threshold={layout.minimum_match_score:.3f}, "
            f"references={len(layout.reference_images)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
