from __future__ import annotations

from devpipe.ui.actions import load_defaults, set_field_value
from devpipe.ui.app import DevpipeTextualApp
from devpipe.ui.screens.config_screen import ConfigScreen
from devpipe.ui.state import FieldKind, FieldMeta, UIState


def test_build_run_config_collects_custom_fields_and_overrides(tmp_path):
    app = DevpipeTextualApp(project_root=tmp_path)
    state = load_defaults(
        UIState(),
        profile="",
        available_profiles=[],
        available_stages=["architect", "developer", "qa_local"],
        fields=[
            FieldMeta(key="task_id", label="Task ID", kind=FieldKind.STRING, section="custom"),
            FieldMeta(key="dataset", label="Dataset", kind=FieldKind.MULTI_SELECT, section="custom"),
        ],
        defaults={
            "task": "Ship it",
            "task_id": "MRC-123",
            "runner": "codex",
            "model": "high",
            "effort": "extra",
            "target_branch": "release1",
            "namespace": "u1",
            "service": "acquiring",
            "tags": ["go"],
            "dataset": ["s4-3ds"],
        },
    )
    app._ui_state = state

    config = app.build_run_config()

    assert config.task_id == "MRC-123"
    assert config.model == "high"
    assert config.effort == "extra"
    assert config.extra_params == {"dataset": ["s4-3ds"]}


def test_derived_inputs_refresh_legacy_fields_when_stage_range_changes(tmp_path):
    devpipe_dir = tmp_path / ".devpipe"
    (devpipe_dir / "tags" / "acquiring-service" / "qa_stand").mkdir(parents=True)
    (devpipe_dir / "config.yaml").write_text(
        """
defaults:
  runner: codex
  service: acquiring
  tags:
    - acquiring-service
""".strip(),
        encoding="utf-8",
    )
    (devpipe_dir / "tags" / "acquiring-service" / "qa_stand" / "params.yaml").write_text(
        """
params:
  - key: dataset
    description: Test dataset
    required: true
    multi: true
    available:
      - s4-3ds
""".strip(),
        encoding="utf-8",
    )

    app = DevpipeTextualApp(project_root=tmp_path)
    app._load_initial_state()
    assert "dataset" in {field.key for field in app._ui_state.form.fields}

    app._ui_state = set_field_value(app._ui_state, "last_role", "qa_local")
    app.on_config_screen_derived_inputs_changed(ConfigScreen.DerivedInputsChanged())

    assert "dataset" not in {field.key for field in app._ui_state.form.fields}


def test_derived_inputs_refresh_preserves_selected_nav_item(tmp_path):
    devpipe_dir = tmp_path / ".devpipe"
    (devpipe_dir / "tags" / "acquiring-service" / "qa_stand").mkdir(parents=True)
    (devpipe_dir / "config.yaml").write_text(
        """
defaults:
  runner: codex
  service: acquiring
  tags:
    - acquiring-service
""".strip(),
        encoding="utf-8",
    )
    (devpipe_dir / "tags" / "acquiring-service" / "qa_stand" / "params.yaml").write_text(
        """
params:
  - key: dataset
    description: Test dataset
    required: true
    multi: true
    available:
      - s4-3ds
""".strip(),
        encoding="utf-8",
    )

    app = DevpipeTextualApp(project_root=tmp_path)
    app._load_initial_state()
    app._ui_state.selected_nav_index = next(
        index for index, item in enumerate(app._ui_state.nav_items) if item.key == "last_role"
    )
    app._ui_state = set_field_value(app._ui_state, "last_role", "qa_local")

    app.on_config_screen_derived_inputs_changed(ConfigScreen.DerivedInputsChanged())

    assert app._ui_state.selected_nav_item is not None
    assert app._ui_state.selected_nav_item.key == "last_role"


def test_derived_inputs_refresh_keeps_normalized_first_role(tmp_path):
    devpipe_dir = tmp_path / ".devpipe"
    (devpipe_dir / "tags" / "acquiring-service" / "qa_stand").mkdir(parents=True)
    (devpipe_dir / "config.yaml").write_text(
        """
defaults:
  runner: codex
  service: acquiring
  tags:
    - acquiring-service
""".strip(),
        encoding="utf-8",
    )

    app = DevpipeTextualApp(project_root=tmp_path)
    app._load_initial_state()
    app._ui_state = set_field_value(app._ui_state, "first_role", "release")
    app._ui_state = set_field_value(app._ui_state, "last_role", "developer")

    app.on_config_screen_derived_inputs_changed(ConfigScreen.DerivedInputsChanged())

    assert app._ui_state.form.values["first_role"] == "developer"
    assert app._ui_state.form.values["last_role"] == "developer"


def test_build_run_config_ignores_hidden_legacy_top_level_fields(tmp_path):
    app = DevpipeTextualApp(project_root=tmp_path)
    state = load_defaults(
        UIState(),
        profile="",
        available_profiles=[],
        available_stages=["architect", "developer", "qa_local", "release", "qa_stand"],
        fields=[
            FieldMeta(key="task_id", label="Task ID", kind=FieldKind.STRING, section="custom"),
        ],
        defaults={
            "task": "Ship it",
            "task_id": "MRC-123",
            "runner": "codex",
            "service": "acquiring",
            "namespace": "u1",
            "tags": ["acquiring-service"],
            "target_branch": "release1",
            "first_role": "architect",
            "last_role": "developer",
        },
    )
    app._ui_state = state

    config = app.build_run_config()

    assert config.task_id == "MRC-123"
    assert config.service is None
    assert config.namespace is None
    assert config.target_branch is None
    assert config.tags == ["acquiring-service"]
