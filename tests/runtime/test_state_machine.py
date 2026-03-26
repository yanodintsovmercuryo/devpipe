from __future__ import annotations

from devpipe.runtime.engine import PipelineEngine
from devpipe.runtime.events import Event, EventType
from devpipe.runtime.retry import RetryPolicy
from devpipe.runtime.state import PipelineState


def test_state_machine_happy_path() -> None:
    engine = PipelineEngine(retry_policy=RetryPolicy.default())
    state = PipelineState.create(task_id="MRC-1", task_text="Ship feature", selected_runner="codex")

    state = engine.apply(state, Event(EventType.RUN_STARTED))

    assert state.current_stage == "architect"
    assert state.status == "running"

    for stage in ["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"]:
        assert state.current_stage == stage
        state = engine.apply(state, Event(EventType.STAGE_COMPLETED, stage=stage, summary=f"{stage} ok"))

    assert state.status == "completed"
    assert state.current_stage == "completed"
    assert state.artifacts["stage_summaries"]["qa_local"] == "qa_local ok"


def test_stage_failure_schedules_retry() -> None:
    engine = PipelineEngine(retry_policy=RetryPolicy(stage_limits={"architect": 2}))
    state = PipelineState.create(task_id="MRC-2", task_text="Retry me", selected_runner="codex")
    state = engine.apply(state, Event(EventType.RUN_STARTED))

    state = engine.apply(
        state,
        Event(EventType.STAGE_FAILED, stage="architect", error_message="transient failure"),
    )

    assert state.status == "retrying"
    assert state.current_stage == "architect"
    assert state.attempt_counters["architect"] == 1
    assert state.last_error == "transient failure"


def test_stage_failure_exhausts_retries() -> None:
    engine = PipelineEngine(retry_policy=RetryPolicy(stage_limits={"architect": 1}))
    state = PipelineState.create(task_id="MRC-3", task_text="Fail me", selected_runner="codex")
    state = engine.apply(state, Event(EventType.RUN_STARTED))

    state = engine.apply(state, Event(EventType.STAGE_FAILED, stage="architect", error_message="boom"))
    state = engine.apply(state, Event(EventType.STAGE_FAILED, stage="architect", error_message="boom again"))

    assert state.status == "failed"
    assert state.current_stage == "architect"
    assert state.last_error == "boom again"
