from __future__ import annotations

from copy import deepcopy

from devpipe.runtime.events import Event, EventType
from devpipe.runtime.retry import RetryPolicy
from devpipe.runtime.transitions import first_stage, next_stage, should_retry_stage
from devpipe.runtime.state import PipelineState
from devpipe.runtime.routing import RuleEvaluator


class PipelineEngine:
    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        routing: "RoutingSpec | None" = None,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy.default()
        self.routing = routing
        self.rule_evaluator = RuleEvaluator(routing) if routing else None

    def apply(self, state: PipelineState, event: Event) -> PipelineState:
        new_state = deepcopy(state)
        new_state.artifacts.setdefault("events", []).append(
            {"event_type": event.event_type.value, "stage": event.stage, "summary": event.summary, "error_message": event.error_message}
        )

        if event.event_type == EventType.RUN_STARTED:
            new_state.status = "running"
            if self.rule_evaluator:
                # Use profile's start_stage
                new_state.current_stage = self.routing.start_stage  # type: ignore
            else:
                # Legacy fallback
                new_state.current_stage = first_stage()
            return new_state

        if event.event_type == EventType.STAGE_COMPLETED:
            if event.stage:
                new_state.artifacts.setdefault("stage_summaries", {})[event.stage] = event.summary

            # Determine next stage
            if self.rule_evaluator:
                # Build context from state
                context = {
                    "inputs": new_state.inputs or {},
                    "stages": new_state.artifacts.get("stage_outputs", {}),
                    "context": new_state.shared_context or {},
                    "runtime": new_state.runtime or {},
                    "integration": new_state.integration or {},
                }
                next_stage_name = self.rule_evaluator.evaluate(event.stage or new_state.current_stage, context)
                # Capture which rule was selected
                new_state.last_selected_rule = context.get("_last_matched_rule")
            else:
                next_stage_name = next_stage(event.stage or new_state.current_stage)

            if next_stage_name == "completed":
                new_state.status = "completed"
                new_state.current_stage = "completed"
            else:
                new_state.status = "running"
                new_state.current_stage = next_stage_name
            new_state.last_error = None
            return new_state

        if event.event_type == EventType.STAGE_FAILED:
            stage = event.stage or new_state.current_stage
            attempts = new_state.attempt_counters.get(stage, 0) + 1
            new_state.attempt_counters[stage] = attempts
            new_state.last_error = event.error_message
            if should_retry_stage(stage, attempts - 1, self.retry_policy):
                new_state.status = "retrying"
                new_state.current_stage = stage
            else:
                new_state.status = "failed"
                new_state.current_stage = stage
            return new_state

        return new_state
