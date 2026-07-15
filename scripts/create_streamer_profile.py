#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one measured facecam profile")
    parser.add_argument("--id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--source-width", type=int, required=True)
    parser.add_argument("--source-height", type=int, required=True)
    parser.add_argument("--facecam-x", type=int, required=True)
    parser.add_argument("--facecam-y", type=int, required=True)
    parser.add_argument("--facecam-width", type=int, required=True)
    parser.add_argument("--facecam-height", type=int, required=True)
    parser.add_argument(
        "--position",
        choices=[
            "top_left",
            "top_right",
            "bottom_left",
            "bottom_right",
            "left",
            "right",
            "center",
            "unknown",
        ],
        required=True,
    )
    args = parser.parse_args()
    if not PROFILE_ID.fullmatch(args.id):
        print("Profile id must contain lowercase letters, digits, underscores or hyphens.", file=sys.stderr)
        return 1
    destination = Path("data/profiles") / f"{args.id}.json"
    if destination.exists():
        print(f"Refusing to overwrite {destination}", file=sys.stderr)
        return 1
    value = {
        "version": 1,
        "id": args.id,
        "display_name": args.display_name,
        "source_resolution": {"width": args.source_width, "height": args.source_height},
        "layouts": [
            {
                "id": args.position,
                "type": "small_facecam",
                "facecam_region": {
                    "x": args.facecam_x,
                    "y": args.facecam_y,
                    "width": args.facecam_width,
                    "height": args.facecam_height,
                },
                "position": args.position,
            }
        ],
        "vertical": {"layout": "face_top_content_bottom", "facecam_height_ratio": 0.38},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(f"Created {destination}. Validate it with scripts/validate_streamer_profile.py {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
