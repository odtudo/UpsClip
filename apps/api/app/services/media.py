import json
import re
from pathlib import Path
from typing import Any

from ..config import Settings
from ..timecodes import format_timestamp
from .edit_plan import SilenceInterval
from .process import ProcessError, run_command
from .setup_status import cookies_path

SILENCE_START = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")


def _twitch_args(settings: Settings) -> list[str | Path]:
    path = cookies_path(settings)
    return ["--cookies", path] if path and path.is_file() else []


def _friendly_twitch_error(exc: ProcessError) -> RuntimeError:
    detail = exc.stderr.lower()
    if "login required" in detail or "cookies" in detail or "subscriber" in detail:
        return RuntimeError(
            "This Twitch VOD requires an authorized session. Export Netscape-format cookies, "
            "save them under data/credentials, and set TWITCH_COOKIES_PATH."
        )
    if "not found" in detail or "does not exist" in detail or "deleted" in detail:
        return RuntimeError("The Twitch VOD is unavailable, deleted, or the URL is incorrect.")
    if "private" in detail or "restricted" in detail:
        return RuntimeError("The Twitch VOD is restricted and cannot be accessed with the current session.")
    return RuntimeError(str(exc))


def inspect_vod(source_url: str, settings: Settings) -> dict[str, Any]:
    try:
        result = run_command(
            [
                settings.ytdlp_path,
                *_twitch_args(settings),
                "--dump-single-json",
                "--skip-download",
                "--no-playlist",
                source_url,
            ],
            label="VOD metadata inspection",
            timeout=120,
        )
    except ProcessError as exc:
        raise _friendly_twitch_error(exc) from exc
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("yt-dlp returned invalid VOD metadata") from exc


def download_section(
    source_url: str,
    start_seconds: int,
    end_seconds: int,
    destination: Path,
    settings: Settings,
) -> tuple[Path, float]:
    margin_start = max(0.0, start_seconds - settings.download_margin_seconds)
    margin_end = end_seconds + settings.download_margin_seconds
    destination.mkdir(parents=True, exist_ok=True)
    template = destination / "download.%(ext)s"
    try:
        result = run_command(
            [
                settings.ytdlp_path,
                *_twitch_args(settings),
                "--no-playlist",
                "--download-sections",
                f"*{format_timestamp(margin_start)}-{format_timestamp(margin_end)}",
                "--force-keyframes-at-cuts",
                "--merge-output-format",
                "mp4",
                "--print",
                "after_move:filepath",
                "-o",
                template,
                source_url,
            ],
            label="VOD section download",
            timeout=7200,
        )
    except ProcessError as exc:
        raise _friendly_twitch_error(exc) from exc
    printed_paths = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
    candidates = [path for path in printed_paths if path.exists()]
    if not candidates:
        candidates = sorted(destination.glob("download.*"))
    if not candidates:
        raise RuntimeError("yt-dlp completed without producing a media file")
    return candidates[-1].resolve(), margin_start


def precise_trim(
    source: Path,
    destination: Path,
    offset_seconds: float,
    duration: float,
    settings: Settings,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            settings.ffmpeg_path,
            "-y",
            "-ss",
            f"{offset_seconds:.3f}",
            "-i",
            source,
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            settings.video_preset,
            "-crf",
            str(settings.video_crf),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            destination,
        ],
        label="Precise video trim",
        timeout=7200,
    )


def create_demo_clip(destination: Path, duration: float, settings: Settings) -> None:
    duration = max(2.0, min(duration, 30.0))
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            settings.ffmpeg_path,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=1280x720:rate=25:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration}",
            "-vf",
            "drawtext=text='Demo clip':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=60",
            "-af",
            "volume=0:enable='between(t,3,5)+between(t,9,12)'",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "25",
            "-c:a",
            "aac",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            destination,
        ],
        label="Demo video generation",
        timeout=180,
    )


def probe_media(path: Path, settings: Settings) -> dict[str, Any]:
    result = run_command(
        [
            settings.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration,size:stream=index,codec_type,codec_name,width,height,"
                "r_frame_rate,pix_fmt,sample_rate,channels,sample_aspect_ratio,duration"
            ),
            "-of",
            "json",
            path,
        ],
        label="Media inspection",
        timeout=60,
    )
    return json.loads(result.stdout)


def media_duration(path: Path, settings: Settings) -> float:
    return float(probe_media(path, settings)["format"]["duration"])


def detect_silences(path: Path, settings: Settings) -> list[SilenceInterval]:
    try:
        result = run_command(
            [
                settings.ffmpeg_path,
                "-hide_banner",
                "-i",
                path,
                "-af",
                f"silencedetect=noise=-35dB:d={settings.silence_min_seconds}",
                "-f",
                "null",
                "-",
            ],
            label="Audio silence analysis",
            timeout=3600,
        )
    except ProcessError as exc:
        if "matches no streams" in exc.stderr or "does not contain any stream" in exc.stderr:
            return []
        raise
    intervals: list[SilenceInterval] = []
    current_start: float | None = None
    for line in result.stderr.splitlines():
        if match := SILENCE_START.search(line):
            current_start = float(match.group(1))
        elif match := SILENCE_END.search(line):
            end = float(match.group(1))
            if current_start is not None and end > current_start:
                intervals.append(SilenceInterval(current_start, end))
            current_start = None
    if current_start is not None:
        intervals.append(SilenceInterval(current_start, media_duration(path, settings)))
    return intervals


def render_edit_plan(
    source: Path,
    destination: Path,
    plan: dict[str, Any],
    *,
    normalize_audio: bool,
    output_format: str,
    settings: Settings,
) -> None:
    segments = plan["segments"]
    if not segments:
        raise RuntimeError("The edit plan contains no video segments")
    probe = probe_media(source, settings)
    has_audio = any(stream.get("codec_type") == "audio" for stream in probe["streams"])
    filters: list[str] = []
    for index, segment in enumerate(segments):
        start, end = segment["source_start"], segment["source_end"]
        video_filter = f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS"
        if output_format == "vertical":
            video_filter += (
                ",crop='min(iw,ih*9/16)':ih:(iw-ow)/2:0,"
                f"scale={settings.vertical_output_width}:{settings.vertical_output_height},setsar=1"
            )
        filters.append(f"{video_filter}[v{index}]")
        if has_audio:
            filters.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{index}]")

    if has_audio:
        ordered = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
        filters.append(f"{ordered}concat=n={len(segments)}:v=1:a=1[vcat][acat]")
    else:
        ordered = "".join(f"[v{i}]" for i in range(len(segments)))
        filters.append(f"{ordered}concat=n={len(segments)}:v=1:a=0[vcat]")

    filters.append("[vcat]format=yuv420p[vout]")
    if has_audio:
        if normalize_audio:
            filters.append("[acat]loudnorm=I=-16:LRA=11:TP=-1.5[aout]")
        else:
            filters.append("[acat]anull[aout]")

    args: list[str | Path] = [settings.ffmpeg_path, "-y", "-i", source, "-filter_complex", ";".join(filters)]
    args.extend(["-map", "[vout]"])
    if has_audio:
        args.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    args.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            settings.video_preset,
            "-crf",
            str(settings.video_crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            destination,
        ]
    )
    run_command(args, label="Final video rendering", timeout=7200)
