#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.app.config import get_settings  # noqa: E402
from apps.api.app.services.setup_status import get_setup_status  # noqa: E402


def main() -> int:
    settings = get_settings()
    settings.ensure_directories()
    status = get_setup_status(settings)
    labels = {
        "ffmpeg_available": "FFmpeg",
        "ffprobe_available": "ffprobe",
        "ytdlp_available": "yt-dlp",
        "data_writable": "Data directory writable",
        "database_accessible": "SQLite database",
        "youtube_client_secret_present": "YouTube client secret",
        "youtube_token_present": "YouTube token",
        "youtube_token_usable": "YouTube token valid/renewable",
        "twitch_cookies_present": "Optional Twitch cookies",
    }
    for key, label in labels.items():
        optional = key == "twitch_cookies_present"
        value = bool(status[key])
        marker = "OPTIONAL" if optional and not value else "OK" if value else "MISSING"
        print(f"{marker:8} {label}")
    for message in status["messages"]:
        print(f"INFO     {message}")
    core_keys = (
        "ffmpeg_available",
        "ffprobe_available",
        "ytdlp_available",
        "data_writable",
        "database_accessible",
    )
    core = all(status[key] for key in core_keys)
    print("\nCore processing is ready." if core else "\nCore processing is not ready.")
    youtube_message = (
        "YouTube is ready."
        if status["youtube_ready"]
        else "YouTube still needs valid Desktop OAuth credentials and authorization."
    )
    print(youtube_message)
    return 0 if core else 1


if __name__ == "__main__":
    raise SystemExit(main())
