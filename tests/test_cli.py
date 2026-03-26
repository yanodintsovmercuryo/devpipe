from __future__ import annotations

from pathlib import Path

import pytest

from devpipe.cli import build_parser, main


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
