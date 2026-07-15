import subprocess

import pytest

from apps.api.app.services.process import ProcessError, run_command


def test_subprocess_failure_is_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["fake"], 2, "", "first line\nReadable failure\n")

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(ProcessError, match="Readable failure") as raised:
        run_command(["fake", "--flag"], label="Fake command")
    assert raised.value.returncode == 2
    assert raised.value.command == ["fake", "--flag"]


def test_missing_executable_is_mapped() -> None:
    with pytest.raises(ProcessError, match="Executable not found"):
        run_command(["/definitely/not/a/real/executable"], label="Missing command")
