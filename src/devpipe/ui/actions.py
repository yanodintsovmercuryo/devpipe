"""Pure state transitions (actions/reducers) for the UI.

Each function takes UIState (or relevant sub-state) and returns a new state.
No Textual or I/O here.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from devpipe.ui.state import (
    FieldEditorState,
    FieldKind,
    FieldMeta,
    FormState,
    NavSection,
    RunViewState,
    StageAttempt,
    UIState,
    build_nav_items,
    derive_status_bar,
)


def load_defaults(
    state: UIState,
    profile: str,
    available_profiles: list[str],
    available_stages: list[str],
    fields: list[FieldMeta],
    defaults: dict[str, Any],
) -> UIState:
    """Initialize form with profile metadata and default values."""
    new = deepcopy(state)
    new.form.profile = profile
    new.form.available_profiles = available_profiles
    new.form.available_stages = available_stages
    new.form.fields = fields
    new.form.values = dict(defaults)

    # Ensure standard field defaults
    new.form.values.setdefault("profile", profile)
    new.form.values.setdefault("task", "")
    new.form.values.setdefault("runner", "auto")
    new.form.values.setdefault("model", "auto")
    new.form.values.setdefault("effort", "auto")
    new.form.values.setdefault("first_role", available_stages[0] if available_stages else "")
    new.form.values.setdefault("last_role", available_stages[-1] if available_stages else "")

    new.nav_items = build_nav_items(new.form)
    new.status_bar = derive_status_bar(new.form)
    new.selected_nav_index = 0
    new.editor = FieldEditorState()
    return new


def select_nav_item(state: UIState, index: int) -> UIState:
    """Move cursor to a specific nav item."""
    new = deepcopy(state)
    if 0 <= index < len(new.nav_items):
        new.selected_nav_index = index
    return new


def select_profile(
    state: UIState,
    profile: str,
    fields: list[FieldMeta],
    defaults: dict[str, Any],
    available_stages: list[str],
) -> UIState:
    """Switch profile — resets custom fields, keeps standard values where valid."""
    new = deepcopy(state)
    old_values = new.form.values.copy()

    new.form.profile = profile
    new.form.fields = fields
    new.form.available_stages = available_stages

    # Keep standard values that are still valid
    new.form.values = dict(defaults)
    new.form.values["profile"] = profile
    for key in ("task", "runner", "model", "effort"):
        if key in old_values:
            new.form.values[key] = old_values[key]

    # Validate first_role / last_role against new stages
    old_first = old_values.get("first_role", "")
    old_last = old_values.get("last_role", "")
    if old_first in available_stages:
        new.form.values["first_role"] = old_first
    else:
        new.form.values["first_role"] = available_stages[0] if available_stages else ""
    if old_last in available_stages:
        new.form.values["last_role"] = old_last
    else:
        new.form.values["last_role"] = available_stages[-1] if available_stages else ""

    # Validate runner
    if new.form.values.get("runner") not in new.form.available_runners:
        new.form.values["runner"] = "auto"

    new.nav_items = build_nav_items(new.form)
    new.status_bar = derive_status_bar(new.form)
    new.editor = FieldEditorState()

    # Reset nav selection if needed
    if new.selected_nav_index >= len(new.nav_items):
        new.selected_nav_index = 0

    return new


def set_field_value(state: UIState, key: str, value: Any) -> UIState:
    """Set a form field value."""
    new = deepcopy(state)
    new.form.values[key] = value
    stages = new.form.available_stages
    first = new.form.values.get("first_role")
    last = new.form.values.get("last_role")
    if stages and first in stages and last in stages:
        first_index = stages.index(first)
        last_index = stages.index(last)
        if first_index > last_index:
            if key == "first_role":
                new.form.values["last_role"] = first
            elif key == "last_role":
                new.form.values["first_role"] = last
    new.status_bar = derive_status_bar(new.form)
    return new


def begin_inline_edit(state: UIState, field_key: str) -> UIState:
    """Open inline editor for a field."""
    new = deepcopy(state)
    current_value = new.form.values.get(field_key, "")
    new.editor = FieldEditorState(
        field_key=field_key,
        editing=True,
        draft_value=current_value,
    )
    return new


def cancel_inline_edit(state: UIState) -> UIState:
    """Cancel inline editor without applying."""
    new = deepcopy(state)
    new.editor = FieldEditorState()
    return new


def apply_inline_edit(state: UIState) -> UIState:
    """Apply inline edit value to form."""
    new = deepcopy(state)
    if new.editor.editing and new.editor.field_key:
        new.form.values[new.editor.field_key] = new.editor.draft_value
        new.status_bar = derive_status_bar(new.form)
    new.editor = FieldEditorState()
    return new


def apply_history_entry(state: UIState, entry: dict[str, Any]) -> UIState:
    """Load values from a history entry into the form."""
    new = deepcopy(state)

    field_mapping = {
        "task": "task",
        "task_id": "task_id",
        "runner": "runner",
        "model": "model",
        "effort": "effort",
        "target_branch": "target_branch",
        "service": "service",
        "namespace": "namespace",
        "tags": "tags",
        "first_role": "first_role",
        "last_role": "last_role",
    }

    for hist_key, form_key in field_mapping.items():
        if hist_key in entry:
            new.form.values[form_key] = entry[hist_key]

    # Merge extra params
    extra = entry.get("extra_params", {})
    for k, v in extra.items():
        new.form.values[k] = v

    # Validate runner
    if new.form.values.get("runner") not in new.form.available_runners:
        new.form.values["runner"] = "auto"

    # Validate stages
    stages = new.form.available_stages
    if new.form.values.get("first_role") not in stages:
        new.form.values["first_role"] = stages[0] if stages else ""
    if new.form.values.get("last_role") not in stages:
        new.form.values["last_role"] = stages[-1] if stages else ""

    new.status_bar = derive_status_bar(new.form)
    new.editor = FieldEditorState()
    return new


def start_run(state: UIState, run_id: str, stages: list[str], runner: str, model: str, effort: str) -> UIState:
    """Transition to run state."""
    new = deepcopy(state)
    new.active_screen = "run"
    new.run_view = RunViewState(
        run_id=run_id,
        status="running",
        timeline=[],
        runner_name=runner,
        model_name=model,
        effort=effort,
    )
    for s in stages:
        new.run_view.timeline.append(StageAttempt(stage=s, attempt_number=1, status="pending"))
    return new


def append_run_output(state: UIState, text: str) -> UIState:
    """Append output lines to the run log."""
    new = deepcopy(state)
    lines = text.split("\n")
    new.run_view.log_lines.extend(lines)
    return new


def complete_stage_attempt(
    state: UIState,
    stage: str,
    status: str = "done",
    summary: str = "",
    error: str = "",
) -> UIState:
    """Mark a stage attempt as done/failed in the timeline."""
    new = deepcopy(state)
    for attempt in new.run_view.timeline:
        if attempt.stage == stage and attempt.status == "active":
            attempt.status = status
            attempt.summary = summary
            attempt.error = error
            break
    return new


def begin_stage(state: UIState, stage: str, runner: str, model: str, effort: str) -> UIState:
    """Mark a stage as active in the timeline."""
    new = deepcopy(state)
    new.run_view.active_stage = stage
    new.run_view.runner_name = runner
    new.run_view.model_name = model
    new.run_view.effort = effort

    for attempt in new.run_view.timeline:
        if attempt.stage == stage and attempt.status == "active":
            return new

    # Find the pending attempt for this stage and activate it
    for attempt in new.run_view.timeline:
        if attempt.stage == stage and attempt.status == "pending":
            attempt.status = "active"
            break
    else:
        # Retry: add a new attempt
        existing = [a for a in new.run_view.timeline if a.stage == stage]
        attempt_num = len(existing) + 1
        new.run_view.timeline.append(
            StageAttempt(stage=stage, attempt_number=attempt_num, status="active")
        )

    return new


def finish_run(state: UIState, status: str, run_id: str) -> UIState:
    """Mark the run as complete."""
    new = deepcopy(state)
    new.run_view.status = status
    new.run_view.run_id = run_id
    return new
