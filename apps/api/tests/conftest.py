from pathlib import Path

import pytest

from apps.api.app.config import Settings


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        database_url=None,
        youtube_client_secrets_path=tmp_path / "data/credentials/client_secret.json",
        youtube_token_path=tmp_path / "data/credentials/token.json",
        face_detector_model_path=tmp_path / "models/missing-yunet.onnx",
        max_clip_duration_seconds=120,
    )
