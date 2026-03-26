from __future__ import annotations

from pathlib import Path

import pytest

from devpipe.app import OrchestratorApp, RunConfig
from devpipe.roles.envelope import TaskResult
from devpipe.roles.loader import RoleDefinition


def _role(name: str) -> RoleDefinition:
    return RoleDefinition(
        name=name,
        runner="codex",
        prompt=f"Prompt for {name}",
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
        allowed_inputs=["task"],
        produced_outputs=[name],
        retry_limit=1,
    )


def _roles() -> dict[str, RoleDefinition]:
    return {name: _role(name) for name in ["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"]}


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


def test_full_pipeline_success(tmp_path: Path) -> None:
    runner = FakeRunner()
    app = OrchestratorApp(
        roles=_roles(),
        runners={"codex": runner},
        runs_dir=tmp_path / "runs",
        namespace_map=None,
        jira_adapter=None,
        git_adapter=None,
        github_adapter=None,
        kubernetes_adapter=None,
    )

    result = app.run(
        RunConfig(
            task_id="MRC-42",
            task="Deliver full pipeline",
            runner="codex",
            deploy_branch="release1-4",
            stand="u1",
            dataset="s4-3ds",
            namespace="explicit-ns",
            service="acquiring",
        )
    )

    assert result.status == "completed"
    assert result.release_context["namespace"] == "explicit-ns"
    assert runner.calls == ["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"]


def test_full_pipeline_fails_without_namespace_mapping(tmp_path: Path) -> None:
    app = OrchestratorApp(
        roles=_roles(),
        runners={"codex": FakeRunner()},
        runs_dir=tmp_path / "runs",
        namespace_map=None,
        jira_adapter=None,
        git_adapter=None,
        github_adapter=None,
        kubernetes_adapter=None,
    )

    with pytest.raises(ValueError):
        app.run(
            RunConfig(
                task_id="MRC-43",
                task="Release pipeline",
                runner="codex",
                deploy_branch="release1-4",
                stand="u1",
                dataset="s4-3ds",
                namespace=None,
                service="acquiring",
            )
        )


def test_full_pipeline_stops_on_github_failure(tmp_path: Path) -> None:
    class FailingGitHub:
        def ensure_workflow_success(self, _run_id: str) -> None:
            raise RuntimeError("workflow failed")

    app = OrchestratorApp(
        roles=_roles(),
        runners={"codex": FakeRunner()},
        runs_dir=tmp_path / "runs",
        namespace_map=None,
        jira_adapter=None,
        git_adapter=None,
        github_adapter=FailingGitHub(),
        kubernetes_adapter=None,
    )

    with pytest.raises(RuntimeError):
        app.run(
            RunConfig(
                task_id="MRC-44",
                task="Release pipeline",
                runner="codex",
                deploy_branch="release1-4",
                stand="u1",
                dataset="s4-3ds",
                namespace="ns",
                service="acquiring",
            )
        )


def test_full_pipeline_stops_on_kubernetes_timeout(tmp_path: Path) -> None:
    class FailingKubernetes:
        def wait_until_ready(self, namespace: str, service: str, attempts: int = 10):
            raise RuntimeError(f"{namespace}/{service} not ready")

    app = OrchestratorApp(
        roles=_roles(),
        runners={"codex": FakeRunner()},
        runs_dir=tmp_path / "runs",
        namespace_map=None,
        jira_adapter=None,
        git_adapter=None,
        github_adapter=None,
        kubernetes_adapter=FailingKubernetes(),
    )

    with pytest.raises(RuntimeError):
        app.run(
            RunConfig(
                task_id="MRC-45",
                task="Release pipeline",
                runner="codex",
                deploy_branch="release1-4",
                stand="u1",
                dataset="s4-3ds",
                namespace="ns",
                service="acquiring",
            )
        )
