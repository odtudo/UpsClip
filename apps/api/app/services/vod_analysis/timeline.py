import json
import os
from pathlib import Path

from .schemas import CoarseTimeline, LayoutTimeline, PhaseTimeline


def load_timeline(path: Path, cache_key: str) -> CoarseTimeline | None:
    try:
        value = CoarseTimeline.model_validate_json(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None
    return value if value.cache_key == cache_key else None


def persist_timeline(path: Path, timeline: CoarseTimeline) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    payload = json.dumps(timeline.model_dump(mode="json"), indent=2, ensure_ascii=False)
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def copy_timeline(source: Path, destination: Path) -> None:
    value = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, destination)


def load_phase_timeline(path: Path, expected_key: str) -> PhaseTimeline | None:
    try:
        value = PhaseTimeline.model_validate_json(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None
    return value if value.phase_cache_key == expected_key else None


def persist_phase_timeline(path: Path, timeline: PhaseTimeline) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    payload = json.dumps(timeline.model_dump(mode="json"), indent=2, ensure_ascii=False)
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def load_layout_timeline(path: Path, expected_key: str) -> LayoutTimeline | None:
    try:
        value = LayoutTimeline.model_validate_json(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None
    return value if value.cache_key == expected_key else None


def persist_layout_timeline(path: Path, timeline: LayoutTimeline) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(timeline.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temporary, path)
