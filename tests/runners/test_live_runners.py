from __future__ import annotations

import shutil
import subprocess

import pytest


pytestmark = pytest.mark.live_runner


@pytest.mark.parametrize(
    ("binary", "args"),
    [
        ("codex", ["--version"]),
        ("claude", ["--version"]),
    ],
)
def test_live_runner_cli_is_callable(binary: str, args: list[str]) -> None:
    assert shutil.which(binary), f"{binary} is not available in PATH"

    completed = subprocess.run(
        [binary, *args],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() or completed.stderr.strip()
