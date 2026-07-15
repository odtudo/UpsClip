#!/usr/bin/env python3
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.app.config import Settings  # noqa: E402
from apps.api.app.services.media import probe_media  # noqa: E402
from apps.api.app.services.process import run_command  # noqa: E402
from apps.api.app.services.subtitles import burn_subtitles, transcribe_media, write_ass  # noqa: E402


def main() -> int:
    persistent_data = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    settings = Settings(
        data_dir=persistent_data,
        database_url=None,
        whisper_model=os.environ.get("SMOKE_WHISPER_MODEL", "tiny"),
        whisper_device="cpu",
        whisper_compute_type="int8",
        whisper_language="en",
        video_preset="ultrafast",
        video_crf=26,
    )
    settings.ensure_directories()
    with tempfile.TemporaryDirectory(prefix="vertical-subtitle-smoke-") as temporary:
        root = Path(temporary)
        source = root / "vertical-speech.mp4"
        subtitles = root / "captions.ass"
        rendered = root / "rendered.mp4"
        run_command(
            [
                settings.ffmpeg_path,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x342060:s=720x1280:r=25:d=6",
                "-f",
                "lavfi",
                "-i",
                "flite=text='This is a vertical video with automatic captions':voice=slt",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-c:a",
                "aac",
                "-shortest",
                "-pix_fmt",
                "yuv420p",
                source,
            ],
            label="Vertical speech fixture",
            timeout=180,
        )
        captions = transcribe_media(source, settings)
        write_ass(captions, subtitles, vertical=True)
        burn_subtitles(source, subtitles, rendered, settings)
        info = probe_media(rendered, settings)
        video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
        if (video["width"], video["height"]) != (720, 1280) or not rendered.is_file():
            print("Vertical subtitle smoke test failed: invalid rendered video", file=sys.stderr)
            return 1
        print(
            f"Vertical subtitle smoke test passed: {len(captions)} captions, "
            f"{video['width']}x{video['height']}, burned-in MP4"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
