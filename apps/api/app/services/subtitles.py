import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..config import Settings
from .process import run_command


@dataclass(frozen=True)
class Caption:
    start: float
    end: float
    text: str


def _caption_groups(words: Iterable[object], max_words: int = 5, max_chars: int = 32) -> list[Caption]:
    captions: list[Caption] = []
    group: list[object] = []
    for word in words:
        text = str(getattr(word, "word", "")).strip()
        if not text:
            continue
        prospective = " ".join([*(str(getattr(item, "word", "")).strip() for item in group), text])
        if group and (len(group) >= max_words or len(prospective) > max_chars):
            captions.append(_caption_from_words(group))
            group = []
        group.append(word)
    if group:
        captions.append(_caption_from_words(group))
    return captions


def _caption_from_words(words: list[object]) -> Caption:
    text = " ".join(str(getattr(word, "word", "")).strip() for word in words).strip()
    return Caption(
        start=max(0.0, float(getattr(words[0], "start", 0.0) or 0.0)),
        end=max(0.1, float(getattr(words[-1], "end", 0.0) or 0.0)),
        text=text,
    )


def transcribe_media(source: Path, settings: Settings) -> list[Caption]:
    model_root = settings.data_dir / "models"
    huggingface_cache = model_root / "huggingface"
    cache_root = model_root / "cache"
    huggingface_cache.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(huggingface_cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        import ctranslate2
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Local subtitles require faster-whisper. Install the API requirements or rebuild Docker."
        ) from exc

    device = settings.whisper_device
    if device == "auto":
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    compute_type = settings.whisper_compute_type
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    language = None if settings.whisper_language == "auto" else settings.whisper_language
    try:
        model = WhisperModel(
            settings.whisper_model,
            device=device,
            compute_type=compute_type,
            download_root=str(model_root),
        )
        segments, _ = model.transcribe(
            str(source),
            language=language,
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )
        words = [word for segment in segments for word in (segment.words or [])]
    except Exception as exc:
        raise RuntimeError(
            f"Local Whisper transcription failed with model '{settings.whisper_model}': {exc}"
        ) from exc
    captions = _caption_groups(words)
    if not captions:
        raise RuntimeError("Whisper found no speech to subtitle in this clip.")
    return captions


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{fraction:02d}"


def _ass_text(value: str, max_line_chars: int = 18) -> str:
    clean = re.sub(r"\s+", " ", value).strip().replace("{", "(").replace("}", ")")
    words = clean.split()
    lines: list[str] = []
    line: list[str] = []
    for word in words:
        if line and len(" ".join([*line, word])) > max_line_chars:
            lines.append(" ".join(line))
            line = []
        line.append(word)
    if line:
        lines.append(" ".join(line))
    return r"\N".join(lines[:2])


def write_ass(
    captions: list[Caption],
    destination: Path,
    *,
    vertical: bool,
    width: int | None = None,
    height: int | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    width = width or (1080 if vertical else 1280)
    height = height or (1920 if vertical else 720)
    font_size = 88 if vertical else 42
    margin_v = 240 if vertical else 70
    style_format = (
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    style = (
        f"Style: Shorts,DejaVu Sans,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        f"&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,45,45,{margin_v},1"
    )
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
{style_format}
{style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [
        f"Dialogue: 0,{_ass_time(item.start)},{_ass_time(item.end)},Shorts,,0,0,0,,{_ass_text(item.text)}"
        for item in captions
        if item.end > item.start
    ]
    destination.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def _filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")


def burn_subtitles(source: Path, subtitles: Path, destination: Path, settings: Settings) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            settings.ffmpeg_path,
            "-y",
            "-i",
            source,
            "-vf",
            f"ass='{_filter_path(subtitles)}'",
            "-c:v",
            "libx264",
            "-preset",
            settings.video_preset,
            "-crf",
            str(settings.video_crf),
            "-c:a",
            "copy",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            destination,
        ],
        label="Subtitle burn-in",
        timeout=7200,
    )
