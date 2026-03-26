from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    TASK_CONTEXT_LOADED = "task_context_loaded"
    STAGE_REQUESTED = "stage_requested"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    RETRY_SCHEDULED = "retry_scheduled"
    RELEASE_REQUESTED = "release_requested"
    RELEASE_FAILED = "release_failed"
    STAND_TEST_REQUESTED = "qa_stand_requested"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"


@dataclass
class Event:
    event_type: EventType
    stage: str | None = None
    summary: str | None = None
    error_message: str | None = None
    payload: dict[str, object] = field(default_factory=dict)
