import json
import os
import socket
import webbrowser
from pathlib import Path
from typing import Callable

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ..config import Settings

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class YouTubeConfigurationError(RuntimeError):
    pass


def _validate_client_secret(path: Path) -> None:
    if not path.is_file():
        raise YouTubeConfigurationError(
            "YouTube client secrets are missing. Place the Google Desktop app JSON at "
            "data/credentials/client_secret.json."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise YouTubeConfigurationError("client_secret.json is not valid JSON.") from exc
    installed = payload.get("installed") if isinstance(payload, dict) else None
    if (
        not isinstance(installed, dict)
        or not installed.get("client_id")
        or not installed.get("client_secret")
    ):
        raise YouTubeConfigurationError(
            "client_secret.json is not a Google OAuth Desktop app credential. "
            "Create an OAuth client with application type Desktop app."
        )


def authorize(settings: Settings) -> Path:
    _validate_client_secret(settings.youtube_client_secrets_path)
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(settings.youtube_client_secrets_path), SCOPES)
        print("A browser will be opened if available. The authorization URL is also printed below.")
        credentials = flow.run_local_server(
            host="localhost",
            port=8080,
            open_browser=True,
            authorization_prompt_message="Open this URL to authorize YouTube:\n{url}",
            success_message="Authorization complete. You may close this browser window.",
        )
    except webbrowser.Error as exc:
        raise YouTubeConfigurationError(
            "No graphical browser is available for OAuth. Run ./scripts/youtube_auth.sh "
            "from the Kali desktop session with DISPLAY/WAYLAND_DISPLAY available."
        ) from exc
    except (OSError, ValueError, socket.error) as exc:
        raise YouTubeConfigurationError(
            "YouTube authorization could not start. Ensure localhost port 8080 is free and retry."
        ) from exc
    if not credentials or not credentials.refresh_token:
        raise YouTubeConfigurationError(
            "Authorization was cancelled or Google did not issue a refresh token. "
            "Revoke the app grant if necessary, then authorize again."
        )
    settings.youtube_token_path.parent.mkdir(parents=True, exist_ok=True)
    settings.youtube_token_path.write_text(credentials.to_json(), encoding="utf-8")
    os.chmod(settings.youtube_token_path, 0o600)
    return settings.youtube_token_path


def _credentials(settings: Settings) -> Credentials:
    _validate_client_secret(settings.youtube_client_secrets_path)
    if not settings.youtube_token_path.exists():
        raise YouTubeConfigurationError("YouTube is not authorized. Run ./scripts/youtube_auth.sh first.")
    try:
        credentials = Credentials.from_authorized_user_file(str(settings.youtube_token_path), SCOPES)
    except (OSError, ValueError, TypeError) as exc:
        raise YouTubeConfigurationError(
            "The YouTube token is invalid. Run ./scripts/youtube_auth.sh again."
        ) from exc
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except RefreshError as exc:
            raise YouTubeConfigurationError(
                "The YouTube refresh token was rejected or revoked. Run ./scripts/youtube_auth.sh again."
            ) from exc
        settings.youtube_token_path.write_text(credentials.to_json(), encoding="utf-8")
        os.chmod(settings.youtube_token_path, 0o600)
    if not credentials.valid:
        raise YouTubeConfigurationError("The YouTube token is invalid. Run ./scripts/youtube_auth.sh again.")
    return credentials


def verify_channel(settings: Settings) -> str:
    youtube = build("youtube", "v3", credentials=_credentials(settings), cache_discovery=False)
    response = youtube.channels().list(part="id,snippet", mine=True).execute()
    items = response.get("items", [])
    if not items:
        raise YouTubeConfigurationError(
            "The authorized Google account has no available YouTube channel. "
            "Create or select a channel, then retry."
        )
    return str(items[0].get("snippet", {}).get("title") or items[0]["id"])


def upload_video(
    video_path: Path,
    *,
    title: str,
    description: str,
    tags: list[str],
    privacy_status: str,
    settings: Settings,
    progress_callback: Callable[[int], None] | None = None,
) -> str:
    youtube = build("youtube", "v3", credentials=_credentials(settings), cache_discovery=False)
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": description, "tags": tags, "categoryId": "20"},
            "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
        },
        media_body=MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True),
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and progress_callback:
            progress_callback(int(status.progress() * 100))
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube upload completed without returning a video ID")
    return str(video_id)
