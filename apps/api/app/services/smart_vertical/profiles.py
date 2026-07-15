from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .geometry import clamp_rect
from .types import ProfileValidationError, Rect

PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
POSITIONS = {
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
    "left",
    "right",
    "center",
    "left_center",
    "right_center",
    "left_column",
    "right_column",
    "unknown",
}
LAYOUT_TYPES = {"small_facecam", "side_facecam", "fullscreen_face"}


def normalize_identity(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def validate_profile(value: dict[str, Any]) -> dict[str, Any]:
    profile_id = value.get("id")
    if value.get("version") != 1 or not isinstance(profile_id, str) or not PROFILE_ID.fullmatch(profile_id):
        raise ProfileValidationError("Profile needs version 1 and a safe id")
    source = value.get("source_resolution") or {}
    width, height = source.get("width"), source.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ProfileValidationError("Profile source resolution must be positive integers")
    ids: set[str] = set()
    for layout in value.get("layouts", []):
        if layout.get("type") not in LAYOUT_TYPES or layout.get("position", "unknown") not in POSITIONS:
            raise ProfileValidationError("Profile contains an unsupported layout")
        if not isinstance(layout.get("id"), str) or layout["id"] in ids:
            raise ProfileValidationError("Profile layout ids must be unique")
        ids.add(layout["id"])
        region = layout.get("facecam_region") or {}
        try:
            rect = Rect(*(int(region[key]) for key in ("x", "y", "width", "height")))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProfileValidationError("Profile facecam region is invalid") from exc
        if rect.x < 0 or rect.y < 0 or rect.width <= 0 or rect.height <= 0:
            raise ProfileValidationError("Profile regions must be positive and inside the source")
        if rect.x + rect.width > width or rect.y + rect.height > height:
            raise ProfileValidationError("Profile region exceeds the source resolution")
        roi = layout.get("content_region_of_interest")
        if roi:
            try:
                roi_rect = Rect(*(int(roi[key]) for key in ("x", "y", "width", "height")))
            except (KeyError, TypeError, ValueError) as exc:
                raise ProfileValidationError("Profile content ROI is invalid") from exc
            if (
                roi_rect.x < 0
                or roi_rect.y < 0
                or roi_rect.width <= 0
                or roi_rect.height <= 0
                or roi_rect.x + roi_rect.width > width
                or roi_rect.y + roi_rect.height > height
            ):
                raise ProfileValidationError("Profile content ROI exceeds the source resolution")
    ratio = (value.get("vertical") or {}).get("facecam_height_ratio", 0.38)
    if not isinstance(ratio, (int, float)) or not 0.25 <= ratio <= 0.55:
        raise ProfileValidationError("facecam_height_ratio must be between 0.25 and 0.55")
    return value


def load_profile(profiles_dir: Path, profile_id: str) -> dict[str, Any]:
    if not PROFILE_ID.fullmatch(profile_id):
        raise ProfileValidationError("Invalid profile id")
    path = (profiles_dir / f"{profile_id}.json").resolve()
    if path.parent != profiles_dir.resolve():
        raise ProfileValidationError("Invalid profile path")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileValidationError(f"Streamer profile '{profile_id}' does not exist") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileValidationError(f"Streamer profile '{profile_id}' is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ProfileValidationError("Profile must be a JSON object")
    return validate_profile(value)


def list_profiles(profiles_dir: Path) -> list[dict[str, str]]:
    profiles = []
    for path in sorted(profiles_dir.glob("*.json")):
        try:
            value = load_profile(profiles_dir, path.stem)
        except ProfileValidationError:
            continue
        profiles.append({"id": value["id"], "display_name": value.get("display_name") or value["id"]})
    return profiles


def resolve_profile(
    profiles_dir: Path, requested: str, uploader: str | None
) -> tuple[dict[str, Any] | None, str]:
    if requested != "auto":
        return load_profile(profiles_dir, requested), "selected_by_user"
    identity = normalize_identity(uploader)
    for item in list_profiles(profiles_dir):
        if identity and normalize_identity(item["id"]) == identity:
            return load_profile(profiles_dir, item["id"]), "matched_vod_uploader"
    return None, "no_profile_match"


def scaled_profile_regions(
    profile: dict[str, Any], width: int, height: int
) -> list[tuple[Rect, dict[str, Any]]]:
    source = profile["source_resolution"]
    result = []
    for layout in profile.get("layouts", []):
        region = layout["facecam_region"]
        rect = Rect(
            round(region["x"] * width / source["width"]),
            round(region["y"] * height / source["height"]),
            round(region["width"] * width / source["width"]),
            round(region["height"] * height / source["height"]),
        )
        result.append((clamp_rect(rect, width, height), layout))
    return result
