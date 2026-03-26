from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from devpipe.roles.envelope import build_envelope
from devpipe.roles.loader import RoleDefinition, load_roles
from devpipe.runtime.engine import PipelineEngine
from devpipe.runtime.events import Event, EventType
from devpipe.runtime.retry import RetryPolicy
from devpipe.runtime.state import STAGE_ORDER, PipelineState
from devpipe.runners.claude import ClaudeRunner
from devpipe.runners.codex import CodexRunner
from devpipe.runners.profile_map import (
    RunnerProfiles,
    load_runner_profiles,
    resolve_effort,
    resolve_model,
)
from devpipe.storage.artifact_store import ArtifactStore
from devpipe.storage.config_store import ConfigStore
from devpipe.storage.run_logger import RunLogger


@dataclass
class RunConfig:
    task_id: str | None
    task: str
    runner: str
    target_branch: str | None = None
    namespace: str | None = None
    service: str | None = None
    tags: list[str] | None = None
    extra_params: dict[str, str | list[str]] | None = None
    first_role: str | None = None
    last_role: str | None = None


class OrchestratorApp:
    def __init__(
        self,
        roles: dict[str, RoleDefinition],
        runners: dict[str, object],
        runs_dir: str | Path,
        jira_adapter=None,
        git_adapter=None,
        github_adapter=None,
        kubernetes_adapter=None,
        retry_policy: RetryPolicy | None = None,
        project_root: str | Path | None = None,
        runner_profiles: RunnerProfiles | None = None,
    ) -> None:
        self.roles = roles
        self.runners = runners
        self.runs_dir = Path(runs_dir)
        self.jira_adapter = jira_adapter
        self.git_adapter = git_adapter
        self.github_adapter = github_adapter
        self.kubernetes_adapter = kubernetes_adapter
        self.engine = PipelineEngine(retry_policy=retry_policy)
        self.project_root = Path(project_root) if project_root is not None else None
        self.runner_profiles = runner_profiles or {}

    def run(
        self,
        config: RunConfig,
        on_stage_start: "Callable[[str, str, str, str], None] | None" = None,
        on_stage_complete: "Callable[[str, dict], None] | None" = None,
    ) -> PipelineState:
        from devpipe.history import save_run
        save_run(config)

        first_role = config.first_role or STAGE_ORDER[0]
        last_role = config.last_role or STAGE_ORDER[-1]

        if first_role not in STAGE_ORDER:
            raise ValueError(f"Unknown first_role: {first_role}")
        if last_role not in STAGE_ORDER:
            raise ValueError(f"Unknown last_role: {last_role}")
        if STAGE_ORDER.index(first_role) > STAGE_ORDER.index(last_role):
            raise ValueError(f"first_role '{first_role}' must come before last_role '{last_role}'")

        task_id = config.task_id or "no-id"
        state = PipelineState.create(task_id=task_id, task_text=config.task, selected_runner=config.runner)
        state.release_context.update({**(config.extra_params or {})})

        if self.jira_adapter is not None and config.task_id:
            state.shared_context["jira"] = self.jira_adapter.fetch_issue(config.task_id)

        logger = RunLogger(self.runs_dir, state.run_id)
        artifacts = ArtifactStore(logger.run_dir)

        event = Event(EventType.RUN_STARTED, payload={"task_id": task_id})
        logger.log_event(event)
        state = self.engine.apply(state, event)
        state.current_stage = first_role

        while state.status not in {"completed", "failed"}:
            role = self.roles[state.current_stage]
            actual_runner_name = role.runner if config.runner == "auto" else config.runner
            runner = self.runners[actual_runner_name]
            state.selected_runner = actual_runner_name
            resolved_model = resolve_model(self.runner_profiles, actual_runner_name, role.model)
            resolved_effort = resolve_effort(self.runner_profiles, actual_runner_name, role.effort)
            runner.model_name = resolved_model
            runner.effort = resolved_effort
            stage_context: dict[str, object] = {"config": config.__dict__}
            if state.current_stage == "release":
                if not config.target_branch:
                    raise ValueError("target_branch must be provided for release stage")
                if not config.namespace:
                    raise ValueError("namespace must be provided for release stage")
                if not config.service:
                    raise ValueError("service must be provided for release stage")
                current_branch = getattr(self.git_adapter, "current_branch", lambda: None)() if self.git_adapter is not None else None
                stage_context["release_inputs"] = {
                    "branch": current_branch,
                    "target_branch": config.target_branch,
                    "namespace": config.namespace,
                    "service": config.service,
                    **(config.extra_params or {}),
                }

            envelope = build_envelope(
                role,
                state,
                model_name=resolved_model,
                effort=resolved_effort,
                extra_context=stage_context,
                project_root=self.project_root,
                tags=config.tags,
            )
            if on_stage_start is not None:
                on_stage_start(state.current_stage, actual_runner_name, resolved_model, resolved_effort)
            try:
                result = runner.run(envelope)
            except Exception as exc:
                failure = Event(EventType.STAGE_FAILED, stage=state.current_stage, error_message=str(exc))
                logger.log_event(failure)
                state = self.engine.apply(state, failure)
                logger.write_summary(state)
                if state.status == "failed":
                    raise
                continue

            state.artifacts.setdefault("stage_outputs", {})[role.name] = result.structured_output
            transcript_path = logger.log_stage_transcript(role.name, result.transcript)
            artifacts.write_stage_artifacts(role.name, result.structured_output)
            state.shared_context[f"{role.name}_log"] = str(transcript_path)

            if on_stage_complete is not None:
                on_stage_complete(role.name, result.structured_output)

            success = Event(EventType.STAGE_COMPLETED, stage=role.name, summary=result.summary)
            logger.log_event(success)
            state = self.engine.apply(state, success)
            logger.write_summary(state)

            if role.name == last_role and state.status not in {"completed", "failed"}:
                state.status = "completed"
                state.current_stage = "completed"
                logger.write_summary(state)

            if role.name == "release" and self.github_adapter is not None:
                self.github_adapter.ensure_workflow_success(state.run_id)

        logger.write_summary(state)
        return state

    def inspect_roles(self) -> list[str]:
        return sorted(self.roles)


def build_default_app(base_dir: str | Path) -> OrchestratorApp:
    base = Path(base_dir)
    config_store = ConfigStore(base / "config" / "runners.yaml")
    raw_config = config_store.load()
    runner_config = raw_config.get("runners", {})
    runner_profiles = load_runner_profiles(raw_config)
    roles = load_roles(base / "roles")

    codex_config = runner_config.get("codex", {})
    claude_config = runner_config.get("claude", {})
    runners = {
        "codex": CodexRunner(
            command=codex_config.get("command", ["codex"]),
            timeout=int(codex_config.get("timeout", 300)),
        ),
        "claude": ClaudeRunner(
            command=claude_config.get("command", ["claude"]),
            timeout=int(claude_config.get("timeout", 300)),
        ),
    }

    return OrchestratorApp(
        roles=roles,
        runners=runners,
        runs_dir=base / "runs",
        project_root=Path.cwd(),
        runner_profiles=runner_profiles,
    )
