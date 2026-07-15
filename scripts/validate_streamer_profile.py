#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.app.services.smart_vertical.profiles import (  # noqa: E402
    ProfileValidationError,
    validate_profile,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a local Smart Vertical Layout profile")
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.profile.read_text(encoding="utf-8"))
        validate_profile(value)
    except (OSError, json.JSONDecodeError, ProfileValidationError) as exc:
        print(f"Invalid profile: {exc}", file=sys.stderr)
        return 1
    print(f"Profile '{value['id']}' is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
