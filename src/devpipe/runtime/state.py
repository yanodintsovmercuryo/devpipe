from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


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

    @classmethod
    def create(cls, task_id: str, task_text: str, selected_runner: str, run_id: str | None = None) -> "PipelineState":
        actual_run_id = run_id or f"{task_id.lower()}-{uuid4().hex[:8]}"
        return cls(
            run_id=actual_run_id,
            task_id=task_id,
            task_text=task_text,
            status="pending",
            current_stage="pending",
            selected_runner=selected_runner,
            shared_context={"created_at": datetime.now(timezone.utc).isoformat()},
        )
