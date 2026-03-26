from __future__ import annotations

from pathlib import Path

import pytest

from devpipe.app import OrchestratorApp, RunConfig
from devpipe.roles.envelope import TaskResult
from devpipe.roles.loader import RoleDefinition
from devpipe.runners.profile_map import load_runner_profiles


def _role(name: str) -> RoleDefinition:
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


def _roles() -> dict[str, RoleDefinition]:
    return {name: _role(name) for name in ["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"]}


def _runner_profiles():
    return load_runner_profiles(
        {
            "runners": {
                "codex": {
                    "model": {
                        "low": "gpt-5.4-mini",
                        "middle": "gpt-5.3-codex",
                        "high": "gpt-5.4",
                    },
                    "effort": {
                        "low": "low",
                        "middle": "medium",
                        "high": "hight",
                        "extra": "extra-hight",
                    },
                }
            }
        }
    )


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, envelope):
        self.calls.append(envelope.role)
        return TaskResult(
            ok=True,
            summary=f"{envelope.role} ok",
            structured_output={"summary": f"{envelope.role} ok"},
            artifacts={},
            next_hints=[],
            error_type=None,
            error_message=None,
            transcript='{"summary":"ok"}',
        )


def test_full_pipeline_auto_runner_uses_role_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("devpipe.history.save_run", lambda _config: None)
    roles = _roles()
    roles["architect"].runner = "claude"
    codex_runner = FakeRunner()
    claude_runner = FakeRunner()
    app = OrchestratorApp(
        roles=roles,
        runners={"codex": codex_runner, "claude": claude_runner},
        runs_dir=tmp_path / "runs",
        jira_adapter=None,
        git_adapter=None,
        github_adapter=None,
        kubernetes_adapter=None,
        runner_profiles=load_runner_profiles(
            {
                "runners": {
                    "codex": {
                        "model": {"low": "gpt-5.4-mini", "middle": "gpt-5.3-codex", "high": "gpt-5.4"},
                        "effort": {"low": "low", "middle": "medium", "high": "hight", "extra": "extra-hight"},
                    },
                    "claude": {
                        "model": {"low": "Haiku 4.5", "middle": "Sonnet 4.6", "high": "Opus 4.6"},
                        "effort": {"low": "low", "middle": "medium", "high": "hight", "extra": "hight"},
                    },
                }
            }
        ),
    )

    result = app.run(
        RunConfig(
            task_id="MRC-46",
            task="Auto runner pipeline",
            runner="auto",
            target_branch="release1-4",
            namespace="explicit-ns",
            service="acquiring",
            extra_params={"stand": "u1", "dataset": "s4-3ds"},
        )
    )

    assert result.status == "completed"
    assert claude_runner.calls == ["architect"]
    assert codex_runner.calls == ["developer", "test_developer", "qa_local", "release", "qa_stand"]


def test_full_pipeline_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("devpipe.history.save_run", lambda _config: None)
    runner = FakeRunner()
    app = OrchestratorApp(
        roles=_roles(),
        runners={"codex": runner},
        runs_dir=tmp_path / "runs",
        jira_adapter=None,
        git_adapter=None,
        github_adapter=None,
        kubernetes_adapter=None,
        runner_profiles=_runner_profiles(),
    )

    result = app.run(
        RunConfig(
            task_id="MRC-42",
            task="Deliver full pipeline",
            runner="codex",
            target_branch="release1-4",
            namespace="explicit-ns",
            service="acquiring",
            extra_params={"stand": "u1", "dataset": "s4-3ds"},
        )
    )

    assert result.status == "completed"
    assert result.release_context["stand"] == "u1"
    assert runner.calls == ["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"]


def test_full_pipeline_fails_without_namespace_for_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("devpipe.history.save_run", lambda _config: None)
    app = OrchestratorApp(
        roles=_roles(),
        runners={"codex": FakeRunner()},
        runs_dir=tmp_path / "runs",
        jira_adapter=None,
        git_adapter=None,
        github_adapter=None,
        kubernetes_adapter=None,
        runner_profiles=_runner_profiles(),
    )

    with pytest.raises(ValueError):
        app.run(
            RunConfig(
                task_id="MRC-43",
                task="Release pipeline",
                runner="codex",
                target_branch="release1-4",
                namespace=None,
                service="acquiring",
                extra_params={"stand": "u1", "dataset": "s4-3ds"},
            )
        )


def test_full_pipeline_stops_on_github_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("devpipe.history.save_run", lambda _config: None)
    class FailingGitHub:
        def ensure_workflow_success(self, _run_id: str) -> None:
            raise RuntimeError("workflow failed")

    app = OrchestratorApp(
        roles=_roles(),
        runners={"codex": FakeRunner()},
        runs_dir=tmp_path / "runs",
        jira_adapter=None,
        git_adapter=None,
        github_adapter=FailingGitHub(),
        kubernetes_adapter=None,
        runner_profiles=_runner_profiles(),
    )

    with pytest.raises(RuntimeError):
        app.run(
            RunConfig(
                task_id="MRC-44",
                task="Release pipeline",
                runner="codex",
                target_branch="release1-4",
                namespace="ns",
                service="acquiring",
                extra_params={"stand": "u1", "dataset": "s4-3ds"},
            )
        )


def test_full_pipeline_ignores_kubernetes_adapter_for_qa_stand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("devpipe.history.save_run", lambda _config: None)
    class FailingKubernetes:
        def wait_until_ready(self, namespace: str, service: str, attempts: int = 10):
            raise RuntimeError(f"{namespace}/{service} not ready")

    app = OrchestratorApp(
        roles=_roles(),
        runners={"codex": FakeRunner()},
        runs_dir=tmp_path / "runs",
        jira_adapter=None,
        git_adapter=None,
        github_adapter=None,
        kubernetes_adapter=FailingKubernetes(),
        runner_profiles=_runner_profiles(),
    )

    result = app.run(
        RunConfig(
            task_id="MRC-45",
            task="Release pipeline",
            runner="codex",
            target_branch="release1-4",
            namespace="ns",
            service="acquiring",
            extra_params={"stand": "u1", "dataset": "s4-3ds"},
        )
    )

    assert result.status == "completed"
