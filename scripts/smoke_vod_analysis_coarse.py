#!/usr/bin/env python3
import argparse
import time

import httpx


def wait_for_api(base: str) -> None:
    for _ in range(120):
        try:
            if httpx.get(f"{base}/health", timeout=2).is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise TimeoutError("API did not become healthy")


def wait_for_job(base: str, job_id: str, timeout_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_progress = -1
    while time.monotonic() < deadline:
        response = httpx.get(f"{base}/vod-analysis/{job_id}", timeout=10)
        response.raise_for_status()
        job = response.json()
        if job["progress"] != last_progress:
            print(f"{job['progress']}% {job['stage']} ({job['completed_windows']}/{job['total_windows']})")
            last_progress = job["progress"]
        if job["status"] == "completed":
            return job
        if job["status"] == "failed":
            raise RuntimeError(job["error_message"])
        time.sleep(1)
    raise TimeoutError("Coarse analysis did not complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test real coarse VOD sampling")
    parser.add_argument("url")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    base = args.api.rstrip("/")
    wait_for_api(base)
    payload = {"url": args.url, "streamer": "illojuan", "force_reanalyze": True}
    created = httpx.post(f"{base}/vod-analysis", json=payload, timeout=20)
    created.raise_for_status()
    job = wait_for_job(base, created.json()["job_id"], args.timeout)
    timeline = job["result"]["coarse_timeline"]
    assert timeline["completed_windows"] == timeline["total_windows"] > 0
    assert any(window.get("audio") for window in timeline["windows"])
    assert any(window.get("visual", {}).get("sampled") for window in timeline["windows"])
    cached = httpx.post(
        f"{base}/vod-analysis",
        json={"url": args.url, "streamer": "illojuan", "force_reanalyze": False},
        timeout=20,
    )
    cached.raise_for_status()
    assert cached.json()["cached"] is True
    assert cached.json()["job_id"] == job["id"]
    print(
        "Coarse smoke passed: "
        f"{timeline['total_windows']} windows, "
        f"{timeline['bytes_downloaded'] / 1_000_000:.1f} MB estimated media"
    )


if __name__ == "__main__":
    main()
