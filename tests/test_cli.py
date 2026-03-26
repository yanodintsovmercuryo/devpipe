from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from rich.console import Console

from devpipe.cli import _RunProgress, build_parser, main


def test_run_command_parses_required_flags(tmp_path: Path) -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "run",
            "--task-id",
            "MRC-123",
            "--task",
            "Implement pipeline",
            "--runner",
            "codex",
            "--roles-dir",
            str(tmp_path / "roles"),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--tag",
            "go,acquiring",
        ]
    )

    assert args.command == "run"
    assert args.task_id == "MRC-123"
    assert args.task == "Implement pipeline"
    assert args.runner == "codex"
    assert args.tags == ["go", "acquiring"]


def test_inspect_command_prints_role_names(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    roles_dir = tmp_path / "roles"
    (roles_dir / "architect").mkdir(parents=True)
    (roles_dir / "architect" / "role.yaml").write_text("name: architect\nrunner: codex\n", encoding="utf-8")

    exit_code = main(["inspect", "--roles-dir", str(roles_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "architect" in captured.out


def test_run_progress_draw_writes_cursor_home_before_panel(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("devpipe.cli.shutil.get_terminal_size", lambda: os.terminal_size((80, 24)))
    monkeypatch.setattr("devpipe.cli.time.monotonic", lambda: 100.0)

    progress = _RunProgress(
        ["architect", "developer"],
        Console(),
        runner_name="codex",
        model_name="gpt-5.4",
        effort="medium",
    )
    progress.current_stage = "architect"
    progress._buf = ["line1"]

    progress._draw()

    captured = capsys.readouterr().out
    plain = re.sub(r"\x1b\[[0-9;:]*[A-Za-z]", "", captured)
    sgr_sequences = re.findall(r"\x1b\[[0-9;:]*m", captured)
    panel_idx = plain.index("╭")
    line_idx = plain.index("line1")
    first_home_idx = captured.index("\x1b[H")
    sep_idx = plain.rindex("─")
    status_idx = plain.rindex("runner codex")
    stage_idx = plain.rindex("stage 00:00")
    total_idx = plain.rindex("total 00:00")

    assert first_home_idx < panel_idx < line_idx < sep_idx < status_idx
    assert status_idx < stage_idx < total_idx
    assert "status" not in plain
    assert "│ runner codex" not in plain
    assert "\x1b[46m" not in captured
    assert "\x1b[44m" not in captured
    assert any(seq in ("\x1b[2m", "\x1b[90m") for seq in sgr_sequences)
    assert "\x1b[2mrunner\x1b[0m \x1b[2mcodex\x1b[0m" in captured
    assert "\x1b[2mstage\x1b[0m \x1b[97m00:00\x1b[0m" in captured
    assert captured.find("\x1b[H", panel_idx) == -1


def test_run_progress_draw_wraps_long_log_lines_without_truncation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("devpipe.cli.shutil.get_terminal_size", lambda: os.terminal_size((40, 12)))
    monkeypatch.setattr("devpipe.cli.time.monotonic", lambda: 100.0)

    progress = _RunProgress(
        ["architect"],
        Console(),
        runner_name="codex",
        model_name="gpt-5.4",
        effort="medium",
    )
    progress.current_stage = "architect"
    progress._buf = ["x" * 120]

    progress._draw()

    captured = capsys.readouterr().out
    plain = re.sub(r"\x1b\[[0-9;:]*[A-Za-z]", "", captured)

    assert "x" * 30 in plain
    assert plain.count("x" * 30) >= 2
    assert "x" * 120 not in plain
