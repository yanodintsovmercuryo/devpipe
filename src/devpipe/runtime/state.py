from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from devpipe.profiles.routing import RoutingSpec


STAGE_ORDER = ["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"]


@dataclass
class PipelineState:
    run_id: str
    task_id: str
    task_text: str
    status: str
    current_stage: str
    selected_runner: str
    attempt_counters: dict[str, int] = field(default_factory=dict)
    shared_context: dict[str, object] = field(default_factory=dict)
    artifacts: dict[str, object] = field(
        default_factory=lambda: {"stage_summaries": {}, "stage_outputs": {}, "events": []}
    )
    release_context: dict[str, object] = field(default_factory=dict)
    last_error: str | None = None

    # Profile-driven fields
    routing: RoutingSpec | None = None
    inputs: dict[str, object] = field(default_factory=dict)
    runtime: dict[str, object] = field(default_factory=dict)
    integration: dict[str, object] = field(default_factory=dict)
    stage_attempts: list[dict[str, object]] = field(default_factory=list)
    last_selected_rule: dict[str, object] | None = None
    # Temporary storage for current stage inputs before execution
    _current_stage_inputs: dict[str, object] | None = None

    @classmethod
    def create(
        cls,
        task_id: str,
        task_text: str,
        selected_runner: str,
        run_id: str | None = None,
        routing: RoutingSpec | None = None,
    ) -> "PipelineState":
        actual_run_id = run_id or f"{task_id.lower()}-{uuid4().hex[:8]}"
        return cls(
            run_id=actual_run_id,
            task_id=task_id,
            task_text=task_text,
            status="pending",
            current_stage="pending",
            selected_runner=selected_runner,
            shared_context={"created_at": datetime.now(timezone.utc).isoformat()},
            routing=routing,
        )
