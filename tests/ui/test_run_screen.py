"""Tests for the run screen state and event bridge."""
from __future__ import annotations

import pytest

from devpipe.ui.actions import (
    append_run_output,
    begin_stage,
    complete_stage_attempt,
    finish_run,
    load_defaults,
    start_run,
)
from devpipe.ui.state import FieldKind, FieldMeta, UIState


def _make_state() -> UIState:
    fields = [
        FieldMeta(key="task_id", label="Task Id", kind=FieldKind.STRING, section="custom"),
    ]
    state = UIState()
    return load_defaults(
        state,
        profile="current-delivery",
        available_profiles=["current-delivery"],
        available_stages=["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"],
        fields=fields,
        defaults={"task": "Test task", "runner": "auto"},
    )


class TestRunScreen:
    def test_start_run_creates_timeline(self):
        state = _make_state()
        state = start_run(state, "run-1", ["architect", "developer", "qa_local"], "codex", "gpt-5", "medium")
        assert state.active_screen == "run"
        assert len(state.run_view.timeline) == 3
        assert all(a.status == "pending" for a in state.run_view.timeline)

    def test_stage_started_activates_stage(self):
        state = _make_state()
        state = start_run(state, "run-1", ["architect", "developer"], "codex", "gpt-5", "medium")
        state = begin_stage(state, "architect", "codex", "gpt-5", "medium")
        assert state.run_view.active_stage == "architect"
        active = [a for a in state.run_view.timeline if a.status == "active"]
        assert len(active) == 1
        assert active[0].stage == "architect"

    def test_streamed_output(self):
        state = _make_state()
        state = start_run(state, "run-1", ["architect"], "codex", "gpt-5", "medium")
        state = append_run_output(state, "chunk1")
        state = append_run_output(state, "chunk2")
        assert len(state.run_view.log_lines) == 2

    def test_stage_completed(self):
        state = _make_state()
        state = start_run(state, "run-1", ["architect"], "codex", "gpt-5", "medium")
        state = begin_stage(state, "architect", "codex", "gpt-5", "medium")
        state = complete_stage_attempt(state, "architect", "done", summary="Plan ready")
        done = [a for a in state.run_view.timeline if a.status == "done"]
        assert len(done) == 1
        assert done[0].summary == "Plan ready"

    def test_stage_failed(self):
        state = _make_state()
        state = start_run(state, "run-1", ["developer"], "codex", "gpt-5", "medium")
        state = begin_stage(state, "developer", "codex", "gpt-5", "medium")
        state = complete_stage_attempt(state, "developer", "failed", error="Timeout")
        failed = [a for a in state.run_view.timeline if a.status == "failed"]
        assert len(failed) == 1
        assert failed[0].error == "Timeout"

    def test_stage_attempts_in_cycle(self):
        """Test qa_stand -> developer retry cycle produces correct attempt numbers."""
        state = _make_state()
        state = start_run(
            state, "run-1",
            ["developer", "qa_stand"],
            "codex", "gpt-5", "medium",
        )
        # First pass
        state = begin_stage(state, "developer", "codex", "gpt-5", "medium")
        state = complete_stage_attempt(state, "developer", "done", "Code done")
        state = begin_stage(state, "qa_stand", "codex", "gpt-5", "medium")
        state = complete_stage_attempt(state, "qa_stand", "failed", error="Test failed")

        # Retry developer
        state = begin_stage(state, "developer", "codex", "gpt-5", "medium")
        dev_attempts = [a for a in state.run_view.timeline if a.stage == "developer"]
        assert len(dev_attempts) == 2
        assert dev_attempts[0].attempt_number == 1
        assert dev_attempts[1].attempt_number == 2
        assert dev_attempts[0].status == "done"
        assert dev_attempts[1].status == "active"

    def test_run_finished(self):
        state = _make_state()
        state = start_run(state, "run-1", ["architect"], "codex", "gpt-5", "medium")
        state = finish_run(state, "completed", "run-1")
        assert state.run_view.status == "completed"

    def test_run_finished_failed(self):
        state = _make_state()
        state = start_run(state, "run-1", ["architect"], "codex", "gpt-5", "medium")
        state = finish_run(state, "failed", "run-1")
        assert state.run_view.status == "failed"

    def test_return_to_config_after_run(self):
        """After finish_run, active_screen remains run (app handles transition)."""
        state = _make_state()
        state = start_run(state, "run-1", ["architect"], "codex", "gpt-5", "medium")
        state = finish_run(state, "completed", "run-1")
        # The screen is still "run" — app pops it
        assert state.active_screen == "run"
