#!/usr/bin/env python3
import json
import os
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.app.config import Settings  # noqa: E402
from apps.api.app.services.media import probe_media  # noqa: E402
from apps.api.app.services.process import run_command  # noqa: E402
from apps.api.app.services.smart_vertical.renderer import render_composition_plan  # noqa: E402
from apps.api.app.services.subtitles import Caption, burn_subtitles, write_ass  # noqa: E402


def main() -> int:
    data_dir = Path(os.environ.get("DATA_DIR", "data")).resolve()
    root = data_dir / "smoke_tests/smart_vertical/latest"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=data_dir, database_url=None, video_preset="ultrafast", video_crf=27)
    source, composed, final = root / "fixture.mp4", root / "vertical_composed.mp4", root / "final.mp4"
    run_command(
        [
            settings.ffmpeg_path,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=1280x720:r=25:d=6",
            "-f",
            "lavfi",
            "-i",
            "sine=f=440:r=48000:d=6",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            source,
        ],
        label="Smart vertical fixture",
        timeout=180,
    )
    plan = {
        "version": 1,
        "algorithm_version": "smart_vertical_v1",
        "source": {"width": 1280, "height": 720, "duration": 6.0},
        "output": {"width": 1080, "height": 1920},
        "warnings": [],
        "segments": [
            {
                "start": 0.0,
                "end": 2.0,
                "layout": "fullscreen_face",
                "output_crop": {"x": 438, "y": 0, "width": 404, "height": 720},
            },
            {
                "start": 2.0,
                "end": 4.5,
                "layout": "small_facecam",
                "facecam_region": {"x": 20, "y": 20, "width": 360, "height": 260},
                "content_crop": {"x": 630, "y": 0, "width": 650, "height": 720},
            },
            {
                "start": 4.5,
                "end": 6.0,
                "layout": "no_face",
                "output_crop": {"x": 438, "y": 0, "width": 404, "height": 720},
            },
        ],
    }
    (root / "composition_plan.json").write_text(json.dumps(plan, indent=2))
    render_composition_plan(source, composed, plan, root, settings)
    subtitles = root / "subtitles.ass"
    write_ass(
        [Caption(0.4, 2.0, "SMART VERTICAL"), Caption(2.1, 4.2, "FACE AND CONTENT")], subtitles, vertical=True
    )
    burn_subtitles(composed, subtitles, final, settings)
    for name, timestamp in (
        ("fullscreen", 1),
        ("facecam_split", 3),
        ("no_face", 5),
        ("subtitles", 3.5),
        ("transition", 2),
    ):
        run_command(
            [
                settings.ffmpeg_path,
                "-y",
                "-ss",
                str(timestamp),
                "-i",
                final,
                "-frames:v",
                "1",
                root / f"{name}.png",
            ],
            label=f"Extract {name} frame",
            timeout=60,
        )
    info = probe_media(final, settings)
    video = next(item for item in info["streams"] if item["codec_type"] == "video")
    audio = next((item for item in info["streams"] if item["codec_type"] == "audio"), None)
    split = cv2.imread(str(root / "facecam_split.png"))
    visual_ok = bool(
        split is not None
        and float(np.mean(split[:700])) > 5
        and float(np.mean(split[735:])) > 5
        and float(np.mean(cv2.absdiff(split[:700], cv2.resize(split[735:], (1080, 700))))) > 3
    )
    valid_streams = (
        video.get("codec_name") == "h264"
        and video.get("pix_fmt") == "yuv420p"
        and video.get("sample_aspect_ratio") in {"1:1", None}
        and audio
        and audio.get("codec_name") == "aac"
    )
    if (
        (video["width"], video["height"]) != (1080, 1920)
        or not valid_streams
        or not visual_ok
        or abs(float(info["format"]["duration"]) - 6) > 0.25
    ):
        print("Smart vertical smoke failed ffprobe validation", file=sys.stderr)
        return 1
    print(f"Smart vertical smoke passed. Artifacts: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
