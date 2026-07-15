#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.app.config import get_settings  # noqa: E402
from apps.api.app.services.youtube import (  # noqa: E402
    YouTubeConfigurationError,
    authorize,
    verify_channel,
)


def main() -> None:
    settings = get_settings()
    settings.ensure_directories()
    token_path = authorize(settings)
    if not token_path.is_file() or token_path.stat().st_size == 0:
        raise YouTubeConfigurationError("Authorization finished but token.json was not generated.")
    print(f"YouTube authorization saved to {token_path}")
    print(f"Authorized channel: {verify_channel(settings)}")


if __name__ == "__main__":
    try:
        main()
    except (YouTubeConfigurationError, KeyboardInterrupt) as exc:
        raise SystemExit(str(exc)) from exc
