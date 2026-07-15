#!/usr/bin/env python3
import argparse
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the Phase 1 VOD analysis fixture")
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.api.rstrip("/")
    for _ in range(100):
        try:
            health = httpx.get(f"{base}/health", timeout=2)
            if health.is_success:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    else:
        raise TimeoutError("API did not become healthy before the fixture smoke")
    created = httpx.post(
        f"{base}/vod-analysis",
        json={
            "url": "https://www.twitch.tv/videos/123456789",
            "streamer": "illojuan",
            "force_reanalyze": True,
        },
        timeout=10,
    )
    created.raise_for_status()
    job_id = created.json()["job_id"]
    for _ in range(50):
        response = httpx.get(f"{base}/vod-analysis/{job_id}", timeout=10)
        response.raise_for_status()
        job = response.json()
        if job["status"] == "completed":
            candidates = job["result"]["candidates"]
            assert candidates and candidates[0]["score"] >= candidates[-1]["score"]
            print(f"Fixture smoke passed: {len(candidates)} candidates; top score {candidates[0]['score']}")
            return
        if job["status"] == "failed":
            raise RuntimeError(job["error_message"])
        time.sleep(0.1)
    raise TimeoutError("Fixture analysis did not complete")


if __name__ == "__main__":
    main()
