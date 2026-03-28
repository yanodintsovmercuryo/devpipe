"""Tests for the history screen state."""
from __future__ import annotations

import pytest

from devpipe.ui.screens.history_screen import HistoryList
from devpipe.ui.actions import apply_history_entry, load_defaults
from devpipe.ui.state import FieldKind, FieldMeta, UIState
from devpipe.ui.widgets.history_preview import HistoryPreview


def _make_state() -> UIState:
    fields = [
        FieldMeta(key="task_id", label="Task Id", kind=FieldKind.STRING, section="custom"),
        FieldMeta(key="target_branch", label="Target Branch", kind=FieldKind.STRING, section="custom"),
    ]
    state = UIState()
    return load_defaults(
        state,
        profile="current-delivery",
        available_profiles=["current-delivery"],
        available_stages=["architect", "developer", "qa_local"],
        fields=fields,
        defaults={"task": "", "runner": "auto"},
    )


class TestHistoryRestore:
    def test_restore_populates_form(self):
        state = _make_state()
        entry = {
            "date": "2026-03-27 12:00:00",
            "task": "Build feature X",
            "task_id": "MRC-456",
            "runner": "codex",
            "target_branch": "main",
            "service": "acquiring",
            "namespace": "prod",
            "tags": ["go"],
            "extra_params": {"dataset": "full"},
            "first_role": "architect",
            "last_role": "qa_local",
        }
        new = apply_history_entry(state, entry)
        assert new.form.values["task"] == "Build feature X"
        assert new.form.values["task_id"] == "MRC-456"
        assert new.form.values["runner"] == "codex"
        assert new.form.values["target_branch"] == "main"
        assert new.form.values["dataset"] == "full"
        assert new.form.values["first_role"] == "architect"
        assert new.form.values["last_role"] == "qa_local"

    def test_restore_validates_runner(self):
        state = _make_state()
        entry = {"runner": "nonexistent"}
        new = apply_history_entry(state, entry)
        assert new.form.values["runner"] == "auto"

    def test_restore_validates_stages(self):
        state = _make_state()
        entry = {"first_role": "unknown", "last_role": "unknown"}
        new = apply_history_entry(state, entry)
        assert new.form.values["first_role"] == "architect"
        assert new.form.values["last_role"] == "qa_local"

    def test_restore_with_multiple_stage_attempts(self):
        """History entry with stage data should be correctly processed."""
        state = _make_state()
        entry = {
            "task": "Retry test",
            "runner": "auto",
            "first_role": "developer",
            "last_role": "qa_local",
        }
        new = apply_history_entry(state, entry)
        assert new.form.values["first_role"] == "developer"
        assert new.form.values["last_role"] == "qa_local"


def test_history_list_hides_date_and_truncates_multiline_title() -> None:
    hist_list = HistoryList()
    hist_list.set_entries(
        [
            {
                "date": "2026-03-27 12:00:00",
                "task": "First line of task\nSecond line should be hidden because title must stay single-line",
            }
        ]
    )

    rendered = hist_list.render().plain

    assert "2026-03-27" not in rendered
    assert "First line of task" in rendered
    assert "Second line should be hidden" not in rendered


def test_history_list_truncates_to_single_line_with_ellipsis() -> None:
    hist_list = HistoryList()
    hist_list.set_entries(
        [{"task": "Очень длинное название задачи которое обязательно должно быть обрезано в списке истории"}]
    )

    rendered_lines = hist_list.render().plain.splitlines()

    assert rendered_lines[2].endswith("…")
    assert "\n" not in rendered_lines[2]


def test_history_list_removes_large_left_indent() -> None:
    hist_list = HistoryList()
    hist_list.set_entries([{"task": "Build feature X"}])

    rendered_lines = hist_list.render().plain.splitlines()

    assert rendered_lines[2] == "» Build feature X"


def test_history_preview_matches_form_snapshot_layout() -> None:
    preview = HistoryPreview()
    preview.show_entry(
        {
            "date": "2026-03-27 12:00:00",
            "finished_at": "2026-03-27 12:04:00",
            "task": "Build feature X",
            "task_id": "MRC-456",
            "runner": "codex",
            "model": "high",
            "effort": "extra",
            "target_branch": "main",
            "service": "acquiring",
            "namespace": "prod",
            "tags": ["go"],
            "extra_params": {"dataset": ["full"]},
            "first_role": "architect",
            "last_role": "qa_local",
        }
    )

    rendered = preview.render().plain

    assert "Task: Build feature X" in rendered
    assert "Runner: codex" in rendered
    assert "Model: high" in rendered
    assert "Effort: extra" in rendered
    assert "Tags: go" in rendered
    assert "Start Stage: architect" in rendered
    assert "Finish Stage: qa_local" in rendered
    assert "Task Id: MRC-456" in rendered
    assert "Target Branch: main" in rendered
    assert "Service: acquiring" in rendered
    assert "Namespace: prod" in rendered
    assert "Dataset: full" in rendered
    assert "Started: 2026-03-27 12:00:00" in rendered
    assert "Finished: 2026-03-27 12:04:00" in rendered
