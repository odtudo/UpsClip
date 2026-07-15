import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials

from ..config import Settings
from .youtube import SCOPES

YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


def executable_available(value: str) -> bool:
    candidate = Path(value)
    if candidate.is_absolute() or candidate.parent != Path("."):
        return candidate.is_file() and os.access(candidate, os.X_OK)
    return shutil.which(value) is not None


def _json_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def client_secret_valid(path: Path) -> bool:
    payload = _json_object(path)
    desktop = payload.get("installed") if payload else None
    return isinstance(desktop, dict) and bool(desktop.get("client_id") and desktop.get("client_secret"))


def token_usable(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        credentials = Credentials.from_authorized_user_file(str(path), SCOPES)
    except (OSError, ValueError, TypeError):
        return False
    return bool(credentials.valid or credentials.refresh_token)


def data_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="setup-", dir=path, delete=True):
            pass
        return True
    except OSError:
        return False


def database_accessible(path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=3) as connection:
            connection.execute("SELECT 1").fetchone()
        return True
    except (sqlite3.Error, OSError):
        return False


def cookies_path(settings: Settings) -> Path | None:
    path = settings.twitch_cookies_path
    if path is None:
        return None
    root = settings.data_dir.resolve()
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("TWITCH_COOKIES_PATH must point to a file inside DATA_DIR")
    return resolved


def get_setup_status(settings: Settings) -> dict[str, Any]:
    messages: list[str] = []
    secret_present = settings.youtube_client_secrets_path.is_file()
    secret_valid = secret_present and client_secret_valid(settings.youtube_client_secrets_path)
    token_present = settings.youtube_token_path.is_file()
    usable = token_usable(settings.youtube_token_path)
    if not secret_present:
        messages.append("Add the Google Desktop app JSON as data/credentials/client_secret.json.")
    elif not secret_valid:
        messages.append("The YouTube client secret is not a valid Desktop app OAuth JSON file.")
    if secret_valid and not token_present:
        messages.append("Authorize YouTube once with ./scripts/youtube_auth.sh.")
    elif token_present and not usable:
        messages.append("The YouTube token is invalid; authorize the account again.")
    detector_name = "OpenCV YuNet"
    model_present = settings.face_detector_model_path.is_file()
    model_valid = False
    if model_present:
        try:
            digest = hashlib.sha256(settings.face_detector_model_path.read_bytes()).hexdigest()
            model_valid = digest == YUNET_SHA256
        except OSError:
            model_valid = False
    try:
        import cv2

        detector_available = hasattr(cv2, "FaceDetectorYN")
    except ImportError:
        detector_available = False
    smart_vertical_available = detector_available and model_valid
    if not detector_available:
        messages.append("Smart Vertical Layout is unavailable; rebuild the API image with OpenCV YuNet.")
    elif not model_present:
        messages.append("The YuNet face model is missing; run ./scripts/download_face_model.sh.")
    elif not model_valid:
        messages.append("The YuNet face model checksum is invalid; install the verified model again.")
    try:
        cookie_file = cookies_path(settings)
        cookies_present = bool(cookie_file and cookie_file.is_file())
    except ValueError as exc:
        cookies_present = False
        messages.append(str(exc))
    return {
        "ffmpeg_available": executable_available(settings.ffmpeg_path),
        "ffprobe_available": executable_available(settings.ffprobe_path),
        "ytdlp_available": executable_available(settings.ytdlp_path),
        "data_writable": data_writable(settings.data_dir),
        "youtube_client_secret_present": secret_present,
        "youtube_token_present": token_present,
        "youtube_token_usable": usable,
        "youtube_ready": bool(secret_valid and usable),
        "twitch_cookies_present": cookies_present,
        "database_accessible": database_accessible(settings.database_path),
        "face_detector_name": detector_name,
        "face_detector_available": detector_available,
        "face_detector_model_present": model_present,
        "face_detector_model_valid": model_valid,
        "smart_vertical_available": smart_vertical_available,
        "smart_vertical_ready": smart_vertical_available,
        "messages": messages,
    }
