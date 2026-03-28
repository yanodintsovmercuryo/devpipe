from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live-runners",
        action="store_true",
        default=False,
        help="run tests that invoke real codex/claude CLIs",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_runner: invokes real codex/claude CLIs and is skipped by default",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-live-runners"):
        return

    skip_live = pytest.mark.skip(reason="requires --run-live-runners")
    for item in items:
        if "live_runner" in item.keywords:
            item.add_marker(skip_live)
