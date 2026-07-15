#!/usr/bin/env python3
"""Exercise VOD Inspector analysis, timeline, comparison, report, and ZIP export."""

import argparse
import io
import time
import zipfile

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--url", default="https://www.twitch.tv/videos/123456789")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    base = args.api.rstrip("/")
    created = httpx.post(
        f"{base}/vod-inspector",
        json={"url": args.url, "streamer": "illojuan", "force_reanalyze": False},
        timeout=15,
    )
    created.raise_for_status()
    job_id = created.json()["job_id"]
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        response = httpx.get(f"{base}/vod-inspector/{job_id}", timeout=15)
        response.raise_for_status()
        inspector = response.json()
        if inspector["status"] == "completed":
            break
        if inspector["status"] == "failed":
            raise RuntimeError(inspector["error_message"])
        time.sleep(0.25)
    else:
        raise TimeoutError("VOD Inspector smoke timed out")
    assert inspector["phase_timeline"] and inspector["segments"]
    first = inspector["segments"][0]
    notes = {
        "talking_start": 60,
        "talking_end": 90,
        "gameplay_start": 90,
        "gameplay_end": 120,
        "talking_block_2_start": None,
        "talking_block_2_end": None,
        "talking_block_3_start": None,
        "talking_block_3_end": None,
    }
    compared = httpx.put(f"{base}/vod-inspector/{job_id}/validation-notes", json=notes, timeout=15)
    compared.raise_for_status()
    assert compared.json()["metrics"] is not None
    exported = httpx.get(f"{base}/vod-inspector/{job_id}/export", timeout=30)
    exported.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        names = set(archive.namelist())
        required = {
            "metadata.json",
            "layout_timeline.json",
            "phase_timeline.json",
            "timeline.png",
            "summary.md",
            "validation_report.md",
        }
        assert required <= names
        assert "coarse_timeline.json" not in names
        assert not any("credential" in name or "cookie" in name or "token" in name for name in names)
    print(
        {
            "job_id": job_id,
            "segments": len(inspector["segments"]),
            "first_open_url": first["open_url"],
            "zip_files": sorted(names),
        }
    )


if __name__ == "__main__":
    main()
