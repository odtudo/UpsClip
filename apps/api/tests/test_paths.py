from pathlib import Path

import pytest

from apps.api.app.database import safe_data_path


def test_safe_path_accepts_descendant(tmp_path: Path) -> None:
    data = tmp_path / "data"
    candidate = data / "rendered" / "clip.mp4"
    assert safe_data_path(candidate, data) == candidate.resolve()


def test_safe_path_rejects_traversal(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with pytest.raises(ValueError, match="outside"):
        safe_data_path(data / "rendered" / ".." / ".." / "secret", data)
