from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import threading

from devpipe.roles.envelope import build_envelope
from devpipe.roles.loader import RoleDefinition, load_roles
from devpipe.runtime.engine import PipelineEngine
from devpipe.runtime.events import Event, EventType
from devpipe.runtime.retry import RetryPolicy
from devpipe.runtime.state import STAGE_ORDER, PipelineState
from devpipe.runners.claude import ClaudeRunner
from devpipe.runners.codex import CodexRunner
from devpipe.bindings import BindingError, resolve_bindings
from devpipe.profiles.loader import ProfileDefinition
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
    model: str | None = None
    effort: str | None = None
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
        profile: "ProfileDefinition | None" = None,
    ) -> None:
        self.roles = roles
        self.runners = runners
        self.runs_dir = Path(runs_dir)
        self.jira_adapter = jira_adapter
        self.git_adapter = git_adapter
        self.github_adapter = github_adapter
        self.kubernetes_adapter = kubernetes_adapter
        self.profile = profile
        self.engine = PipelineEngine(retry_policy=retry_policy, routing=profile.routing if profile else None)
        self.project_root = Path(project_root) if project_root is not None else None
        self.runner_profiles = runner_profiles or {}
        self._cancel_requested = threading.Event()

    def run(
        self,
        config: RunConfig,
        on_stage_start: "Callable[[str, str, str, str], None] | None" = None,
        on_stage_complete: "Callable[[str, dict], None] | None" = None,
    ) -> PipelineState:
        from devpipe.history import finish_run, save_run
        save_run(config)
        self._cancel_requested.clear()

        # Determine stage bounds based on profile availability
        if self.profile:
            profile_stages = list(self.profile.stages.keys())
            if not profile_stages:
                raise ValueError("Profile has no stages defined")
            default_first = self.profile.routing.start_stage
            default_last = profile_stages[-1]
            first_role = config.first_role or default_first
            last_role = config.last_role or default_last
            available_stages = set(profile_stages)
            stage_order = profile_stages
        else:
            first_role = config.first_role or STAGE_ORDER[0]
            last_role = config.last_role or STAGE_ORDER[-1]
            available_stages = set(STAGE_ORDER)
            stage_order = STAGE_ORDER

        if first_role not in available_stages:
            raise ValueError(f"Unknown first_role: {first_role}")
        if last_role not in available_stages:
            raise ValueError(f"Unknown last_role: {last_role}")
        if stage_order.index(first_role) > stage_order.index(last_role):
            raise ValueError(f"first_role '{first_role}' must come before last_role '{last_role}'")

        task_id = config.task_id or "no-id"
        state = PipelineState.create(
            task_id=task_id,
            task_text=config.task,
            selected_runner=config.runner,
            routing=self.profile.routing if self.profile else None,
        )
        # Populate top-level inputs (available via input.<key>)
        # Includes both standard CLI parameters and extra params
        state.inputs = {
            "task": config.task,
            "task_id": config.task_id or "",
            "target_branch": config.target_branch or "",
            "namespace": config.namespace or "",
            "service": config.service or "",
            "tags": config.tags or [],
            **(config.extra_params or {}),
        }
        state.release_context.update({**(config.extra_params or {})})

        # Runtime info
        if self.git_adapter is not None:
            current_branch = (
                self.git_adapter.current_branch()
                if hasattr(self.git_adapter, "current_branch")
                else None
            )
            state.runtime["git"] = {"current_branch": current_branch}

        # Integration info
        if self.jira_adapter is not None and config.task_id:
            issue = self.jira_adapter.fetch_issue(config.task_id)
            state.integration["jira"] = {"issue": issue}

        logger = RunLogger(self.runs_dir, state.run_id)
        artifacts = ArtifactStore(logger.run_dir)

        event = Event(EventType.RUN_STARTED, payload={"task_id": task_id})
        logger.log_event(event)
        state = self.engine.apply(state, event)
        state.current_stage = first_role

        try:
            while state.status not in {"completed", "failed", "cancelled"}:
                if self._cancel_requested.is_set():
                    state.status = "cancelled"
                    break
                role = self.roles[state.current_stage]
                actual_runner_name = role.runner if config.runner == "auto" else config.runner
                runner = self.runners[actual_runner_name]
                state.selected_runner = actual_runner_name
                model_level = role.model if config.model in {None, "", "auto"} else config.model
                effort_level = role.effort if config.effort in {None, "", "auto"} else config.effort
                resolved_model = resolve_model(self.runner_profiles, actual_runner_name, model_level)
                resolved_effort = resolve_effort(self.runner_profiles, actual_runner_name, effort_level)
                runner.model_name = resolved_model
                runner.effort = resolved_effort
                # Build stage context based on profile bindings (if available)
                if self.profile:
                    stage_spec = self.profile.stages.get(state.current_stage)
                    if stage_spec and stage_spec.in_:
                        # Build resolver context from state
                        resolver_context = {
                            "inputs": state.inputs,
                            "stages": state.artifacts.get("stage_outputs", {}),
                            "context": state.shared_context,
                            "runtime": state.runtime,
                            "integration": state.integration,
                            "_current_stage": state.current_stage,
                        }
                        try:
                            resolved = resolve_bindings(stage_spec.in_.bindings, resolver_context)
                        except BindingError as e:
                            raise RuntimeError(f"Binding resolution failed for stage '{state.current_stage}': {e}") from e
                        stage_context = {"config": config.__dict__, **resolved}
                    else:
                        # No explicit bindings; provide just config
                        stage_context = {"config": config.__dict__}
                else:
                    # Legacy mode: hardcoded context with release special handling
                    stage_context = {"config": config.__dict__}
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

                # Capture stage inputs for attempt tracking (before runner execution)
                state._current_stage_inputs = stage_context.copy()

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
                    if self._cancel_requested.is_set():
                        state.status = "cancelled"
                        logger.write_summary(state)
                        break
                    failure = Event(EventType.STAGE_FAILED, stage=state.current_stage, error_message=str(exc))
                    logger.log_event(failure)
                    state = self.engine.apply(state, failure)
                    logger.write_summary(state)
                    if state.status == "failed":
                        raise
                    continue

                if self._cancel_requested.is_set():
                    state.status = "cancelled"
                    logger.write_summary(state)
                    break

                state.artifacts.setdefault("stage_outputs", {})[role.name] = result.structured_output
                transcript_path = logger.log_stage_transcript(role.name, result.transcript)
                artifacts.write_stage_artifacts(role.name, result.structured_output)
                state.shared_context[f"{role.name}_log"] = str(transcript_path)

                if on_stage_complete is not None:
                    on_stage_complete(role.name, result.structured_output)

                success = Event(EventType.STAGE_COMPLETED, stage=role.name, summary=result.summary)
                logger.log_event(success)
                state = self.engine.apply(state, success)

                # Check for forced completion based on last_role bound
                forced_completion = (
                    role.name == last_role and state.status not in {"completed", "failed"}
                )
                if forced_completion:
                    state.status = "completed"
                    state.current_stage = "completed"

                # Record stage attempt (after final next_stage is determined)
                if state._current_stage_inputs is not None:
                    attempt = {
                        "stage": role.name,
                        "attempt_number": len(state.stage_attempts) + 1,
                        "in_snapshot": state._current_stage_inputs,
                        "out_snapshot": result.structured_output,
                        "selected_rule": state.last_selected_rule,
                        "next_stage": state.current_stage,
                    }
                    state.stage_attempts.append(attempt)
                    state._current_stage_inputs = None
                    state.last_selected_rule = None

                logger.write_summary(state)

                if role.name == "release" and self.github_adapter is not None:
                    self.github_adapter.ensure_workflow_success(state.run_id)
        finally:
            logger.write_summary(state)
            finish_run(config)

        return state

    def inspect_roles(self) -> list[str]:
        return sorted(self.roles)

    def cancel_active_runs(self) -> None:
        self._cancel_requested.set()
        for runner in self.runners.values():
            cancel = getattr(runner, "cancel", None)
            if callable(cancel):
                cancel()


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
