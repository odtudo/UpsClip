#!/usr/bin/env python3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from apps.api.app.config import Settings  # noqa: E402
from apps.api.app.main import create_app  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="twitch-editor-smoke-") as temporary:
        root = Path(temporary)
        settings = Settings(
            data_dir=root / "data",
            database_url=None,
            video_preset="ultrafast",
            video_crf=26,
        )
        app = create_app(settings)
        with TestClient(app) as client:
            response = client.post(
                "/jobs",
                json={
                    "source_url": "https://www.twitch.tv/videos/123456789",
                    "start": "00:00",
                    "end": "00:12",
                    "remove_silences": True,
                    "normalize_audio": True,
                    "output_format": "horizontal",
                    "demo": True,
                },
            )
            response.raise_for_status()
            job_id = response.json()["id"]
            deadline = time.monotonic() + 120
            job = response.json()
            while time.monotonic() < deadline and job["status"] not in {"ready", "failed"}:
                time.sleep(0.25)
                job = client.get(f"/jobs/{job_id}").json()
                print(f"{job['progress']:3d}%  {job['current_step']}")
            if job["status"] != "ready":
                print(f"Smoke test failed: {job.get('error_message') or job['status']}")
                return 1
            video = client.get(f"/jobs/{job_id}/video")
            if video.status_code != 200 or not video.content.startswith(b"\x00\x00"):
                print("Smoke test failed: preview endpoint did not return an MP4")
                return 1
            print(
                f"Smoke test passed: {job['rendered_duration']:.2f}s, "
                f"{job['rendered_size']} bytes, preview HTTP {video.status_code}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
