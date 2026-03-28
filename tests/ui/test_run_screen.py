"""Tests for the run screen state and event bridge."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from devpipe.ui.actions import (
    append_run_output,
    begin_stage,
    complete_stage_attempt,
    finish_run,
    load_defaults,
    start_run,
)
from devpipe.ui.screens.run_screen import LogPanel, RunQuestionPanel, RunScreen, RunStageStrip
from devpipe.ui.state import FieldKind, FieldMeta, UIState
from devpipe.ui.widgets.status_bar import RunStatusBar


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


def test_stage_strip_shows_only_completed_and_active_steps() -> None:
    strip = RunStageStrip()
    state = _make_state()
    state = start_run(state, "run-1", ["architect", "developer", "qa_local"], "codex", "gpt-5", "medium")
    state = begin_stage(state, "architect", "codex", "gpt-5", "medium")
    state.run_view.timeline[0].elapsed_seconds = 12
    state = complete_stage_attempt(state, "architect", "done", summary="done")
    state = begin_stage(state, "developer", "codex", "gpt-5", "medium")
    state.run_view.timeline[1].elapsed_seconds = 8
    strip.set_timeline(state.run_view.timeline)
    strip.set_spinner_frame("⠋")

    rendered = strip.render().plain

    assert "architect" in rendered
    assert "developer" in rendered
    assert "qa_local" not in rendered
    assert "⠋" in rendered
    assert "12s" in rendered
    assert "8s" in rendered


def test_stage_strip_shows_current_pending_step_before_first_start() -> None:
    strip = RunStageStrip()
    state = _make_state()
    state = start_run(state, "run-1", ["architect", "developer"], "codex", "gpt-5", "medium")
    strip.set_timeline(state.run_view.timeline)

    rendered = strip.render().plain

    assert "architect" in rendered
    assert "developer" not in rendered
    assert "No active steps yet" not in rendered


def test_run_status_bar_shows_model_effort_and_total_time() -> None:
    bar = RunStatusBar()

    bar.update_run_state(status="running", elapsed="1m 24s", model="gpt-5", effort="high")

    rendered = bar.render().plain

    assert "running" in rendered
    assert "model gpt-5" in rendered
    assert "effort high" in rendered
    assert "1m 24s" in rendered
    assert "current step" not in rendered


def test_run_status_bar_shows_cancel_confirmation_alert() -> None:
    bar = RunStatusBar()

    bar.show_alert("Stop pipeline? Y — confirm  N — stay")

    rendered = bar.render().plain

    assert "Stop pipeline?" in rendered
    assert "model" not in rendered


def test_run_status_bar_alert_css_is_red() -> None:
    css = RunStatusBar.DEFAULT_CSS

    assert "RunStatusBar.-alert" in css
    assert "$error" in css


def test_question_panel_has_placeholder() -> None:
    panel = RunQuestionPanel()
    widgets = list(panel.compose())

    assert widgets[0].render().plain == "Question"
    assert "No active question yet" in widgets[1].render().plain


def test_log_panel_title_matches_screen_style() -> None:
    panel = LogPanel()
    title = next(panel.compose())

    assert "Output" == title.render().plain


def test_stage_strip_css_adds_vertical_padding() -> None:
    css = RunStageStrip.DEFAULT_CSS

    assert "padding: 1 2;" in css
    assert "height: 5;" in css


def test_run_screen_stage_started_does_not_duplicate_existing_active_attempt() -> None:
    state = _make_state()
    state = start_run(state, "run-1", ["architect", "developer"], "codex", "gpt-5", "medium")
    state = begin_stage(state, "architect", "codex", "gpt-5", "medium")
    screen = RunScreen(state)
    screen.query_one = lambda *_args, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        set_timeline=lambda *_a, **_k: None,
        set_spinner_frame=lambda *_a, **_k: None,
        update_run_state=lambda *_a, **_k: None,
        set_mode=lambda *_a, **_k: None,
        append=lambda *_a, **_k: None,
        show_alert=lambda *_a, **_k: None,
        clear_alert=lambda *_a, **_k: None,
    )

    screen.on_stage_started("architect", "codex", "gpt-5", "medium")

    architect_attempts = [attempt for attempt in screen._state.run_view.timeline if attempt.stage == "architect"]
    assert len(architect_attempts) == 1
    assert architect_attempts[0].status == "active"


def test_log_panel_append_respects_follow_tail_state() -> None:
    panel = LogPanel()
    writes: list[bool | None] = []
    fake_log = SimpleNamespace(
        write=lambda _text, **kwargs: writes.append(kwargs.get("scroll_end")),
    )
    panel.query_one = lambda *_args, **_kwargs: fake_log  # type: ignore[method-assign]

    panel.append("first")
    panel.pause_follow()
    panel.append("second")

    assert writes == [True, False]


def test_run_screen_stage_markers_use_readable_status_messages() -> None:
    state = _make_state()
    screen = RunScreen(state)
    messages: list[str] = []
    screen.query_one = lambda *_args, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        set_timeline=lambda *_a, **_k: None,
        set_spinner_frame=lambda *_a, **_k: None,
        update_run_state=lambda *_a, **_k: None,
        set_mode=lambda *_a, **_k: None,
        append=lambda text, *_a, **_k: messages.append(text),
        show_alert=lambda *_a, **_k: None,
        clear_alert=lambda *_a, **_k: None,
    )

    screen.on_stage_started("architect", "codex", "gpt-5", "medium")
    screen.on_stage_completed("architect", "done")

    assert any("Started: architect" in text for text in messages)
    assert any("Completed: architect" in text for text in messages)


def test_run_screen_shows_cancelled_pipeline_message() -> None:
    state = _make_state()
    screen = RunScreen(state)
    messages: list[str] = []
    screen.query_one = lambda *_args, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        set_timeline=lambda *_a, **_k: None,
        set_spinner_frame=lambda *_a, **_k: None,
        update_run_state=lambda *_a, **_k: None,
        set_mode=lambda *_a, **_k: None,
        append=lambda text, *_a, **_k: messages.append(text),
        show_alert=lambda *_a, **_k: None,
        clear_alert=lambda *_a, **_k: None,
    )

    screen.on_run_finished("cancelled", "run-1")

    assert any("Pipeline cancelled" in text for text in messages)


def test_run_screen_back_while_running_enters_cancel_confirmation() -> None:
    state = _make_state()
    state.run_view.status = "running"
    screen = RunScreen(state)
    status = SimpleNamespace(
        update_run_state=lambda *_a, **_k: None,
        show_alert=lambda *_a, **_k: None,
        clear_alert=lambda *_a, **_k: None,
    )
    question = SimpleNamespace(set_mode=lambda *_a, **_k: None)
    stage_strip = SimpleNamespace(set_timeline=lambda *_a, **_k: None, set_spinner_frame=lambda *_a, **_k: None)
    mapping = {
        "#run-stage-strip": stage_strip,
        "#run-question-panel": question,
        "#run-status": status,
    }
    screen.query_one = lambda selector, *_args, **_kwargs: mapping[selector]  # type: ignore[method-assign]

    screen.action_back()

    assert screen._confirm_cancel is True


def test_run_screen_back_shows_cancel_confirmation_in_status_bar() -> None:
    state = _make_state()
    state.run_view.status = "running"
    screen = RunScreen(state)
    calls: list[str] = []
    status = SimpleNamespace(
        update_run_state=lambda *_a, **_k: None,
        show_alert=lambda message: calls.append(message),
        clear_alert=lambda: calls.append("clear"),
    )
    question = SimpleNamespace(set_mode=lambda *_a, **_k: None)
    stage_strip = SimpleNamespace(set_timeline=lambda *_a, **_k: None, set_spinner_frame=lambda *_a, **_k: None)
    mapping = {
        "#run-stage-strip": stage_strip,
        "#run-question-panel": question,
        "#run-status": status,
    }
    screen.query_one = lambda selector, *_args, **_kwargs: mapping[selector]  # type: ignore[method-assign]

    screen.action_back()

    assert any("Stop pipeline?" in call for call in calls)


def test_run_screen_confirm_cancel_uses_app_async_cancel() -> None:
    state = _make_state()
    state.run_view.status = "running"
    screen = RunScreen(state)
    calls: list[str] = []

    screen._confirm_cancel = True
    screen._begin_cancel_return = lambda: calls.append("cancel")  # type: ignore[method-assign]
    status = SimpleNamespace(
        update_run_state=lambda *_a, **_k: None,
        show_alert=lambda *_a, **_k: None,
        clear_alert=lambda: None,
    )
    question = SimpleNamespace(set_mode=lambda *_a, **_k: None)
    stage_strip = SimpleNamespace(set_timeline=lambda *_a, **_k: None, set_spinner_frame=lambda *_a, **_k: None)
    mapping = {
        "#run-stage-strip": stage_strip,
        "#run-question-panel": question,
        "#run-status": status,
    }
    screen.query_one = lambda selector, *_args, **_kwargs: mapping[selector]  # type: ignore[method-assign]

    screen.action_confirm_cancel()

    assert calls == ["cancel"]
    assert screen._cancelling is True


def test_run_screen_dismiss_cancel_restores_status_bar() -> None:
    state = _make_state()
    state.run_view.status = "running"
    screen = RunScreen(state)
    calls: list[str] = []
    screen._confirm_cancel = True
    status = SimpleNamespace(
        update_run_state=lambda *_a, **_k: None,
        show_alert=lambda message: calls.append(message),
        clear_alert=lambda: calls.append("clear"),
    )
    question = SimpleNamespace(set_mode=lambda *_a, **_k: None)
    stage_strip = SimpleNamespace(set_timeline=lambda *_a, **_k: None, set_spinner_frame=lambda *_a, **_k: None)
    mapping = {
        "#run-stage-strip": stage_strip,
        "#run-question-panel": question,
        "#run-status": status,
    }
    screen.query_one = lambda selector, *_args, **_kwargs: mapping[selector]  # type: ignore[method-assign]

    screen.action_dismiss_cancel()

    assert screen._confirm_cancel is False
    assert "clear" in calls
