import json
import stat
import webbrowser

import pytest

from apps.api.app.services import youtube


class FakeCredentials:
    refresh_token = "test-refresh-token"

    @staticmethod
    def to_json() -> str:
        return '{"refresh_token": "test-refresh-token"}'


class SuccessfulFlow:
    @staticmethod
    def run_local_server(**kwargs):
        return FakeCredentials()


def write_desktop_client(test_settings) -> None:
    test_settings.youtube_client_secrets_path.parent.mkdir(parents=True, exist_ok=True)
    test_settings.youtube_client_secrets_path.write_text(
        json.dumps({"installed": {"client_id": "test-id", "client_secret": "test-secret"}}),
        encoding="utf-8",
    )


def test_authorize_writes_private_reusable_token(test_settings, monkeypatch) -> None:
    write_desktop_client(test_settings)
    monkeypatch.setattr(
        youtube.InstalledAppFlow,
        "from_client_secrets_file",
        lambda *args, **kwargs: SuccessfulFlow(),
    )

    token_path = youtube.authorize(test_settings)

    assert token_path.is_file()
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600


def test_authorize_reports_missing_graphical_browser(test_settings, monkeypatch) -> None:
    write_desktop_client(test_settings)

    class BrowserlessFlow:
        @staticmethod
        def run_local_server(**kwargs):
            raise webbrowser.Error("no browser")

    monkeypatch.setattr(
        youtube.InstalledAppFlow,
        "from_client_secrets_file",
        lambda *args, **kwargs: BrowserlessFlow(),
    )

    with pytest.raises(youtube.YouTubeConfigurationError, match="No graphical browser"):
        youtube.authorize(test_settings)
