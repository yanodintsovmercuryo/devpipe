from __future__ import annotations

from pathlib import Path

from devpipe.roles.envelope import build_envelope
from devpipe.roles.loader import load_roles
from devpipe.runtime.state import PipelineState


def test_loader_reads_role_directories(tmp_path: Path) -> None:
    role_dir = tmp_path / "architect"
    role_dir.mkdir(parents=True)
    (role_dir / "role.yaml").write_text(
        "name: architect\nrunner: codex\nproduces:\n  - plan\nretry_limit: 2\n",
        encoding="utf-8",
    )
    (role_dir / "prompt.md").write_text("You are architect", encoding="utf-8")
    (role_dir / "output.schema.json").write_text(
        '{"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]}',
        encoding="utf-8",
    )

    roles = load_roles(tmp_path)

    assert list(roles) == ["architect"]
    assert roles["architect"].retry_limit == 2
    assert roles["architect"].prompt.startswith("You are architect")


def test_envelope_appends_project_specific_role_rules(tmp_path: Path) -> None:
    role_dir = tmp_path / "architect"
    role_dir.mkdir(parents=True)
    (role_dir / "role.yaml").write_text(
        "name: architect\nrunner: codex\nproduces:\n  - plan\nretry_limit: 2\n",
        encoding="utf-8",
    )
    (role_dir / "prompt.md").write_text("Base architect prompt", encoding="utf-8")
    (role_dir / "output.schema.json").write_text(
        '{"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]}',
        encoding="utf-8",
    )
    composer_dir = tmp_path / ".devpipe"
    composer_dir.mkdir(parents=True)
    (composer_dir / "ARCHITECT_RULES.md").write_text("Read project architecture from project-specific files.", encoding="utf-8")

    role = load_roles(tmp_path)["architect"]
    state = PipelineState.create(task_id="MRC-7", task_text="Plan work", selected_runner="codex")

    envelope = build_envelope(role, state, project_root=tmp_path)

    assert "Base architect prompt" in envelope.instructions
    assert "Project-Specific Rules" in envelope.instructions
    assert "Read project architecture" in envelope.instructions


def test_envelope_appends_tagged_role_rules_after_project_rules(tmp_path: Path) -> None:
    role_dir = tmp_path / "developer"
    role_dir.mkdir(parents=True)
    (role_dir / "role.yaml").write_text(
        "name: developer\nrunner: codex\nproduces:\n  - code\nretry_limit: 2\n",
        encoding="utf-8",
    )
    (role_dir / "prompt.md").write_text("Base developer prompt", encoding="utf-8")
    (role_dir / "output.schema.json").write_text(
        '{"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]}',
        encoding="utf-8",
    )
    composer_dir = tmp_path / ".devpipe"
    composer_dir.mkdir(parents=True)
    (composer_dir / "DEVELOPER_RULES.md").write_text("Repository-specific rules.", encoding="utf-8")
    role = load_roles(tmp_path)["developer"]
    state = PipelineState.create(task_id="MRC-8", task_text="Implement work", selected_runner="codex")

    envelope = build_envelope(role, state, project_root=tmp_path, tags=["go"])

    assert "Base developer prompt" in envelope.instructions
    assert "Repository-specific rules." in envelope.instructions
    assert "## Tagged Rules: go" in envelope.instructions
    assert "Keep dependency interfaces in `external.go`" in envelope.instructions
    assert envelope.instructions.index("Repository-specific rules.") < envelope.instructions.index("## Tagged Rules: go")
