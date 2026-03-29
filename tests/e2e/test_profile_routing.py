"""Tests for profile-driven runtime routing."""
from __future__ import annotations

from pathlib import Path
import yaml

import pytest

from devpipe.app import OrchestratorApp, RunConfig
from devpipe.roles.envelope import TaskResult
from devpipe.roles.loader import RoleDefinition
from devpipe.runners.profile_map import load_runner_profiles
from devpipe.profiles.loader import load_profile


def _simple_role(name: str) -> RoleDefinition:
    return RoleDefinition(
        name=name,
        runner="codex",
        model="middle",
        effort="middle",
        prompt=f"Prompt for {name}",
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
        allowed_inputs=["task"],
        produced_outputs=[name],
        retry_limit=1,
    )


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.outputs: dict[str, dict] = {}

    def run(self, envelope):
        self.calls.append(envelope.role)
        output = self.outputs.get(envelope.role, {"summary": f"{envelope.role} ok"})
        return TaskResult(
            ok=True,
            summary=output.get("summary", f"{envelope.role} ok"),
            structured_output=output,
            artifacts={},
            next_hints=[],
            error_type=None,
            error_message=None,
            transcript='{"summary":"ok"}',
        )


def _create_profile_with_yaml(tmp_dir: Path, pipeline_data: dict) -> "ProfileDefinition":
    profile_dir = tmp_dir / "test-profile"
    profile_dir.mkdir()
    pipeline_path = profile_dir / "pipeline.yml"
    pipeline_path.write_text(yaml.dump(pipeline_data), encoding="utf-8")
    return load_profile("test-profile", builtin_base=tmp_dir)


def test_linear_routing_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that profile with linear routing executes stages in order."""
    monkeypatch.setattr("devpipe.history.save_run", lambda _config: None)
    pipeline = {
        "version": 1,
        "name": "linear-test",
        "defaults": {"runner": "auto"},
        "inputs": {
            "task": {"type": "string", "default": "do it", "custom": True}
        },
        "stages": {
            "stage_a": {"runner": "codex", "model": "middle", "effort": "middle", "out": {"summary": {"type": "string"}}},
            "stage_b": {"runner": "codex", "model": "middle", "effort": "middle", "out": {"summary": {"type": "string"}}},
            "stage_c": {"runner": "codex", "model": "middle", "effort": "middle", "out": {"summary": {"type": "string"}}},
            "completed": {"runner": "codex", "model": "middle", "effort": "middle", "out": {"summary": {"type": "string"}}},
        },
        "routing": {
            "start_stage": "stage_a",
            "by_stage": {
                "stage_a": {"stage": "stage_a", "next_stages": [{"stage": "stage_b", "default": True}]},
                "stage_b": {"stage": "stage_b", "next_stages": [{"stage": "stage_c", "default": True}]},
                "stage_c": {"stage": "stage_c", "next_stages": [{"stage": "completed", "default": True}]},
                "completed": {"stage": "completed", "next_stages": [{"stage": "completed", "default": True}]},
            },
        }
    }
    profile = _create_profile_with_yaml(tmp_path, pipeline)

    roles = {name: _simple_role(name) for name in ["stage_a", "stage_b", "stage_c"]}
    runner = FakeRunner()
    runner_profiles = load_runner_profiles({
        "runners": {
            "codex": {
                "model": {"low": "gpt-5.4-mini", "middle": "gpt-5.3-codex", "high": "gpt-5.4"},
                "effort": {"low": "low", "middle": "medium", "high": "hight", "extra": "extra-hight"},
            }
        }
    })
    app = OrchestratorApp(
        roles=roles,
        runners={"codex": runner},
        runs_dir=tmp_path / "runs",
        profile=profile,
        runner_profiles=runner_profiles,
    )

    result = app.run(RunConfig(task_id="TEST-1", task="Test linear routing", runner="codex"))

    assert result.status == "completed"
    assert runner.calls == ["stage_a", "stage_b", "stage_c"]
    attempt_stages = [a["stage"] for a in result.stage_attempts]
    assert attempt_stages == ["stage_a", "stage_b", "stage_c"]
    assert result.stage_attempts[0]["next_stage"] == "stage_b"
    assert result.stage_attempts[1]["next_stage"] == "stage_c"
    assert result.stage_attempts[2]["next_stage"] == "completed"


def test_branching_routing_based_on_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test routing that branches based on stage output."""
    monkeypatch.setattr("devpipe.history.save_run", lambda _config: None)
    pipeline = {
        "version": 1,
        "name": "branch-test",
        "defaults": {"runner": "auto"},
        "inputs": {
            "task": {"type": "string", "default": "test", "custom": True}
        },
        "stages": {
            "stage_a": {"runner": "codex", "model": "middle", "effort": "middle", "out": {"ok": {"type": "string"}}},
            "stage_b": {"runner": "codex", "model": "middle", "effort": "middle", "out": {"summary": {"type": "string"}}},
            "stage_c": {"runner": "codex", "model": "middle", "effort": "middle", "out": {"summary": {"type": "string"}}},
            "completed": {"runner": "codex", "model": "middle", "effort": "middle", "out": {"summary": {"type": "string"}}},
        },
        "routing": {
            "start_stage": "stage_a",
            "by_stage": {
                "stage_a": {
                    "stage": "stage_a",
                    "next_stages": [
                        {"stage": "stage_b", "all": [{"field": "out.ok", "op": "eq", "value": "yes"}]},
                        {"stage": "stage_c", "default": True},
                    ],
                },
                "stage_b": {"stage": "stage_b", "next_stages": [{"stage": "completed", "default": True}]},
                "stage_c": {"stage": "stage_c", "next_stages": [{"stage": "completed", "default": True}]},
                "completed": {"stage": "completed", "next_stages": [{"stage": "completed", "default": True}]},
            },
        }
    }
    profile = _create_profile_with_yaml(tmp_path, pipeline)

    roles = {name: _simple_role(name) for name in ["stage_a", "stage_b", "stage_c"]}
    runner = FakeRunner()
    runner_profiles = load_runner_profiles({
        "runners": {
            "codex": {
                "model": {"low": "gpt-5.4-mini", "middle": "gpt-5.3-codex", "high": "gpt-5.4"},
                "effort": {"low": "low", "middle": "medium", "high": "hight", "extra": "extra-hight"},
            }
        }
    })
    app = OrchestratorApp(
        roles=roles,
        runners={"codex": runner},
        runs_dir=tmp_path / "runs",
        profile=profile,
        runner_profiles=runner_profiles,
    )

    # Branch to B when A outputs ok="yes"
    runner.outputs["stage_a"] = {"ok": "yes", "summary": "A yes"}
    result = app.run(RunConfig(task_id="TEST-2", task="Branch to B", runner="codex"))
    assert result.status == "completed"
    assert runner.calls == ["stage_a", "stage_b"]
    assert [a["stage"] for a in result.stage_attempts] == ["stage_a", "stage_b"]
    assert result.stage_attempts[0]["next_stage"] == "stage_b"
    assert result.stage_attempts[1]["next_stage"] == "completed"

    # Reset for next run
    runner.calls.clear()
    runner.outputs.clear()
    runner.outputs["stage_a"] = {"ok": "no", "summary": "A no"}
    result = app.run(RunConfig(task_id="TEST-3", task="Branch to C", runner="codex"))
    assert result.status == "completed"
    assert runner.calls == ["stage_a", "stage_c"]
    assert [a["stage"] for a in result.stage_attempts] == ["stage_a", "stage_c"]
    assert result.stage_attempts[0]["next_stage"] == "stage_c"
    assert result.stage_attempts[1]["next_stage"] == "completed"
