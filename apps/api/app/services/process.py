import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


class ProcessError(RuntimeError):
    def __init__(self, label: str, command: Sequence[str], returncode: int, stderr: str):
        detail = _last_useful_line(stderr)
        super().__init__(f"{label} failed{f': {detail}' if detail else ''}")
        self.label = label
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr


def _last_useful_line(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return lines[-1][:500] if lines else ""


def run_command(
    args: Sequence[str | Path],
    *,
    label: str,
    timeout: float | None = None,
) -> CommandResult:
    command = [str(arg) for arg in args]
    logger.info("Running %s: %s", label, " ".join(command[:4]))
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ProcessError(label, command, 127, f"Executable not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProcessError(label, command, 124, f"Command timed out after {timeout} seconds") from exc
    if completed.returncode != 0:
        logger.error("%s failed (%s): %s", label, completed.returncode, completed.stderr[-2000:])
        raise ProcessError(label, command, completed.returncode, completed.stderr)
    return CommandResult(completed.stdout, completed.stderr, completed.returncode)
