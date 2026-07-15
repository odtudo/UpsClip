import json

import pytest

from apps.api.app.services.setup_status import client_secret_valid, cookies_path, token_usable


def test_desktop_client_secret_validation(tmp_path) -> None:
    path = tmp_path / "client_secret.json"
    path.write_text(json.dumps({"installed": {"client_id": "id", "client_secret": "secret"}}))
    assert client_secret_valid(path) is True
    path.write_text(json.dumps({"web": {"client_id": "id", "client_secret": "secret"}}))
    assert client_secret_valid(path) is False


def test_invalid_token_is_not_usable(tmp_path) -> None:
    path = tmp_path / "token.json"
    path.write_text("not-json")
    assert token_usable(path) is False


def test_cookie_path_must_stay_inside_data(test_settings, tmp_path) -> None:
    test_settings.twitch_cookies_path = tmp_path / "outside.txt"
    with pytest.raises(ValueError, match="inside DATA_DIR"):
        cookies_path(test_settings)
