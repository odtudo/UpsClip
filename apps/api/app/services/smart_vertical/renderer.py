from __future__ import annotations

from pathlib import Path

from ..media import media_duration, probe_media
from ..process import ProcessError, run_command
from .types import VerticalRenderError


def render_composition_plan(
    source: Path, destination: Path, plan: dict, work_dir: Path, settings: object, progress=None
) -> dict:
    segment_dir = work_dir / "smart_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segment_paths: list[Path] = []
    for index, segment in enumerate(plan["segments"]):
        if progress:
            progress(
                "composing",
                61 + round(13 * index / max(1, len(plan["segments"]))),
                "Rendering smart vertical layout",
            )
        path = segment_dir / f"segment_{index:03d}.mp4"
        try:
            _render_segment(source, path, segment, settings, plan["source"].get("frame_rate", 30))
        except ProcessError:
            fallback = dict(segment)
            fallback["layout"] = "no_face"
            fallback["output_crop"] = _center_crop(plan["source"], settings)
            _render_segment(source, path, fallback, settings, plan["source"].get("frame_rate", 30))
            plan["warnings"].append(
                {
                    "code": "segment_render_fallback",
                    "start": segment["start"],
                    "end": segment["end"],
                    "message": "A segment used the simple vertical crop after its smart render failed.",
                }
            )
        segment_paths.append(path)
    concat_file = segment_dir / "concat.txt"
    concat_file.write_text(
        "".join(
            f"file '{path.resolve().as_posix().replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
            for path in segment_paths
        ),
        encoding="utf-8",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            settings.ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            destination,
        ],
        label="Smart vertical segment concatenation",
        timeout=7200,
    )
    info = probe_media(destination, settings)
    video_stream = next(item for item in info["streams"] if item.get("codec_type") == "video")
    audio_stream = next((item for item in info["streams"] if item.get("codec_type") == "audio"), None)
    expected = float(plan["source"]["duration"])
    rendered = float(info["format"]["duration"])
    video_duration = float(video_stream.get("duration") or rendered)
    audio_duration = float(audio_stream.get("duration") or rendered) if audio_stream else None
    deltas = [abs(expected - rendered), abs(expected - video_duration)]
    if audio_duration is not None:
        deltas.extend((abs(expected - audio_duration), abs(video_duration - audio_duration)))
    if max(deltas) > 0.25:
        raise VerticalRenderError(
            "Smart vertical output duration mismatch "
            f"(expected={expected:.3f}s video={video_duration:.3f}s audio={audio_duration})"
        )
    if (int(video_stream["width"]), int(video_stream["height"])) != (
        settings.vertical_output_width,
        settings.vertical_output_height,
    ):
        raise VerticalRenderError("Smart vertical output resolution mismatch")
    return {
        "expected_duration": expected,
        "rendered_duration": rendered,
        "video_duration": video_duration,
        "audio_duration": audio_duration,
        "av_delta": abs(video_duration - audio_duration) if audio_duration is not None else 0,
    }


def render_simple_vertical(source: Path, destination: Path, settings: object) -> None:
    probe = probe_media(source, settings)
    video = next(item for item in probe["streams"] if item.get("codec_type") == "video")
    crop = _center_crop({"width": int(video["width"]), "height": int(video["height"])}, settings)
    segment = {
        "start": 0.0,
        "end": media_duration(source, settings),
        "layout": "no_face",
        "output_crop": crop,
    }
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1"
    _render_segment(source, destination, segment, settings, rate)


def _render_segment(
    source: Path, destination: Path, segment: dict, settings: object, frame_rate: float | str
) -> None:
    width, height = settings.vertical_output_width, settings.vertical_output_height
    divider = settings.vertical_divider_height
    layout = segment["layout"]
    if layout == "small_facecam" and segment.get("facecam_region") and segment.get("content_crop"):
        face_height = round((height - divider) * settings.vertical_facecam_height_ratio)
        face_height -= face_height % 2
        content_height = height - divider - face_height
        face = segment["facecam_region"]
        content = segment["content_crop"]
        filters = (
            f"[0:v]crop={face['width']}:{face['height']}:{face['x']}:{face['y']},scale={width}:{face_height}:force_original_aspect_ratio=increase,crop={width}:{face_height},setsar=1[face];"
            f"[0:v]crop={content['width']}:{content['height']}:{content['x']}:{content['y']},scale={width}:{content_height}:force_original_aspect_ratio=increase,crop={width}:{content_height},setsar=1[content];"
            f"color=c=black:s={width}x{divider}:d={segment['end'] - segment['start']}[divider];"
            f"[face][divider][content]vstack=inputs=3,fps={frame_rate},format=yuv420p[vout]"
        )
    else:
        crop = segment.get("output_crop")
        if not crop:
            raise VerticalRenderError("Segment has no valid fallback crop")
        filters = (
            f"[0:v]crop={crop['width']}:{crop['height']}:{crop['x']}:{crop['y']},"
            f"scale={width}:{height},setsar=1,fps={frame_rate},format=yuv420p[vout]"
        )
    args = [
        settings.ffmpeg_path,
        "-y",
        "-ss",
        f"{segment['start']:.3f}",
        "-i",
        source,
        "-t",
        f"{segment['end'] - segment['start']:.3f}",
        "-filter_complex",
        filters,
        "-map",
        "[vout]",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        settings.video_preset,
        "-crf",
        str(settings.video_crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        destination,
    ]
    run_command(args, label="Smart vertical segment render", timeout=7200)


def _center_crop(source: dict, settings: object) -> dict[str, int]:
    width, height = int(source["width"]), int(source["height"])
    target = settings.vertical_output_width / settings.vertical_output_height
    crop_width = min(width, round(height * target))
    crop_width -= crop_width % 2
    return {"x": (width - crop_width) // 2, "y": 0, "width": crop_width, "height": height - height % 2}
