"""Root Textual application for devpipe.

Manages screen routing, UIState, and services container.
Operator Console visual style: graphite dark, cyan/teal accents.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.design import ColorSystem

from devpipe.app import OrchestratorApp, RunConfig, build_default_app
from devpipe.ui.actions import (
    apply_history_entry,
    begin_stage,
    complete_stage_attempt,
    finish_run,
    load_defaults,
    set_field_value,
    start_run,
    append_run_output,
)
from devpipe.ui.run_session import RunEvent, RunSession
from devpipe.ui.screens.config_screen import ConfigScreen
from devpipe.ui.screens.history_screen import HistoryScreen
from devpipe.ui.screens.run_screen import RunScreen
from devpipe.ui.services import (
    discover_profiles,
    load_default_profile,
    load_profile_defaults,
    load_profile_fields,
    load_profile_stages,
    prepare_initial_state,
    resolve_legacy_form_state,
)
from devpipe.ui.state import UIState

# Operator Console color scheme
DEVPIPE_COLORS = {
    "dark": ColorSystem(
        primary="#06b6d4",       # cyan
        secondary="#14b8a6",     # teal
        accent="#22d3ee",        # bright cyan
        warning="#f59e0b",       # amber
        error="#ef4444",         # red
        success="#22c55e",       # green
        background="#1a1a2e",    # deep graphite
        surface="#16213e",       # dark navy
        panel="#0f3460",         # panel blue
    ),
}


class DevpipeTextualApp(App):
    """Devpipe interactive TUI application."""

    TITLE = "devpipe"
    CSS = """
    Screen {
        background: $background;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True, priority=True),
    ]

    def __init__(self, project_root: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._project_root = project_root or Path.cwd()
        self._ui_state = UIState()
        self._result_config: RunConfig | None = None

    def get_default_screen(self) -> ConfigScreen:
        return ConfigScreen(self._ui_state)

    def on_mount(self) -> None:
        """Initialize state and show config screen."""
        self._load_initial_state()
        screen = ConfigScreen(self._ui_state)
        self.push_screen(screen)

    def _load_initial_state(self) -> None:
        """Load profile data and populate UIState."""
        data = prepare_initial_state(self._project_root)
        self._ui_state = load_defaults(
            self._ui_state,
            profile=data["profile"],
            available_profiles=data["available_profiles"],
            available_stages=data["available_stages"],
            fields=data["fields"],
            defaults=data["defaults"],
        )

    # ── Screen event handlers ─────────────────────────────────────────────

    def on_config_screen_profile_changed(self, event: ConfigScreen.ProfileChanged) -> None:
        """Reload fields and stages for new profile."""
        profile = event.profile
        fields = load_profile_fields(profile, self._project_root)
        stages = load_profile_stages(profile, self._project_root)
        defaults = load_profile_defaults(profile, self._project_root)

        from devpipe.ui.actions import select_profile
        self._ui_state = select_profile(
            self._ui_state,
            profile=profile,
            fields=fields,
            defaults=defaults,
            available_stages=stages,
        )

    def on_history_screen_restore_entry(self, event: HistoryScreen.RestoreEntry) -> None:
        """Restore history entry into form state."""
        self._ui_state = apply_history_entry(self._ui_state, event.entry)
        # Refresh config screen
        if self.screen_stack:
            screen = self.screen
            if isinstance(screen, ConfigScreen):
                screen._state = self._ui_state
                screen._update_display()

    def on_config_screen_derived_inputs_changed(self, event: ConfigScreen.DerivedInputsChanged) -> None:
        """Recalculate custom fields for legacy projects when tags or stage range changes."""
        if self._ui_state.form.available_profiles:
            return
        selected_item = self._ui_state.selected_nav_item
        selected_key = selected_item.key if selected_item is not None else None
        data = resolve_legacy_form_state(self._project_root, self._ui_state.form.values)
        allowed_custom_keys = {field.key for field in data["fields"]}
        preserved = {}
        for key, value in self._ui_state.form.values.items():
            if key in {"profile", "task", "runner", "model", "effort", "first_role", "last_role"}:
                preserved[key] = value
            elif key in allowed_custom_keys:
                preserved[key] = value
        defaults = dict(data["defaults"])
        defaults.update(preserved)
        self._ui_state = load_defaults(
            self._ui_state,
            profile=data["profile"],
            available_profiles=data["available_profiles"],
            available_stages=data["available_stages"],
            fields=data["fields"],
            defaults=defaults,
        )
        if selected_key is not None:
            restored_index = next(
                (index for index, item in enumerate(self._ui_state.nav_items) if item.key == selected_key),
                None,
            )
            if restored_index is not None:
                self._ui_state.selected_nav_index = restored_index
        if self.screen_stack:
            screen = self.screen
            if isinstance(screen, ConfigScreen):
                screen._state = self._ui_state
                screen._update_display()

    @property
    def result_config(self) -> RunConfig | None:
        """Return the RunConfig if user completed the form, else None."""
        return self._result_config

    def build_run_config(self) -> RunConfig:
        """Build a RunConfig from current form state."""
        v = self._ui_state.form.values
        visible_custom_keys = {
            field.key for field in self._ui_state.form.fields if field.section == "custom"
        }
        top_level_custom_keys = {"task_id", "target_branch", "namespace", "service", "tags"}
        extra_params = {
            field.key: v[field.key]
            for field in self._ui_state.form.fields
            if field.section == "custom" and field.key not in top_level_custom_keys and field.key in v
        }
        return RunConfig(
            task_id=v.get("task_id") or None,
            task=v.get("task", ""),
            runner=v.get("runner", "auto"),
            model=v.get("model") or None,
            effort=v.get("effort") or None,
            target_branch=v.get("target_branch") if "target_branch" in visible_custom_keys else None,
            namespace=v.get("namespace") if "namespace" in visible_custom_keys else None,
            service=v.get("service") if "service" in visible_custom_keys else None,
            tags=v.get("tags") or [],
            extra_params=extra_params or None,
            first_role=v.get("first_role") or None,
            last_role=v.get("last_role") or None,
        )
