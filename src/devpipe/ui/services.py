"""Service adapters: bridge between UI state layer and project internals.

Reads profiles, history, project config and prepares typed data
for state actions. No Textual imports here.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from devpipe.project_config import load_project_config
from devpipe.runtime.state import STAGE_ORDER
from devpipe.tags import collect_params, load_available_tags, load_tag_definitions
from devpipe.ui.state import FieldKind, FieldMeta


def _git_branch(project_root: Path | None = None) -> str:
    try:
        r = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _task_id_from_branch(branch: str) -> str:
    m = re.match(r"^([A-Z]+-[0-9]+)", branch)
    return m.group(1) if m else ""


def discover_profiles(project_root: Path | None = None) -> list[str]:
    """Find available profile names from .devpipe/profiles/."""
    root = project_root or Path.cwd()
    profiles_dir = root / ".devpipe" / "profiles"
    if not profiles_dir.exists():
        return []
    return sorted(p.name for p in profiles_dir.iterdir() if p.is_dir())


def load_profile_defaults(profile_name: str, project_root: Path | None = None) -> dict[str, Any]:
    """Load default values from a profile's pipeline.yml."""
    root = project_root or Path.cwd()
    pipeline_path = root / ".devpipe" / "profiles" / profile_name / "pipeline.yml"
    if not pipeline_path.exists():
        return {}
    data = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}
    defaults = dict(data.get("defaults", {}))

    # Set runner default
    defaults.setdefault("runner", "auto")

    return defaults


def load_profile_stages(profile_name: str, project_root: Path | None = None) -> list[str]:
    """Extract ordered stage list from profile's flow definition."""
    root = project_root or Path.cwd()
    pipeline_path = root / ".devpipe" / "profiles" / profile_name / "pipeline.yml"
    if not pipeline_path.exists():
        return []
    data = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}

    flow = data.get("flow", {})
    transitions = flow.get("transitions", {})
    start = flow.get("start")
    if not start or not transitions:
        return list(data.get("roles", {}).keys())

    # Walk the flow graph to get ordered stages
    ordered: list[str] = []
    current = start
    visited: set[str] = set()
    while current and current not in {"completed", "failed"} and current not in visited:
        visited.add(current)
        ordered.append(current)
        trans = transitions.get(current, {})
        current = trans.get("on_success")
    return ordered


# Keys managed in the Standard section; exclude from Custom
_STANDARD_KEYS = {"task", "runner", "profile", "first_role", "last_role"}
_LEGACY_TOP_LEVEL_KEYS = _STANDARD_KEYS | {"task_id", "target_branch", "service", "namespace", "tags", "model", "effort"}


def _append_field(fields: list[FieldMeta], seen: set[str], field: FieldMeta) -> None:
    if field.key in seen or field.key in _STANDARD_KEYS:
        return
    fields.append(field)
    seen.add(field.key)


def _infer_kind(default: Any, options: list[str] | None = None, multi: bool = False) -> FieldKind:
    if multi:
        return FieldKind.MULTI_SELECT
    if options:
        return FieldKind.SELECT
    if isinstance(default, list):
        return FieldKind.ARRAY
    if isinstance(default, dict):
        return FieldKind.OBJECT
    if isinstance(default, int):
        return FieldKind.INT
    return FieldKind.STRING


def _normalize_stage_bounds(first_role: str, last_role: str, stages: list[str]) -> tuple[str, str]:
    if not stages:
        return "", ""
    first = first_role if first_role in stages else stages[0]
    last = last_role if last_role in stages else stages[-1]
    if stages.index(first) > stages.index(last):
        last = first
    return first, last


def _legacy_top_level_fields_enabled(active_roles: set[str]) -> bool:
    qa_local_index = STAGE_ORDER.index("qa_local")
    late_roles = set(STAGE_ORDER[qa_local_index:])
    return bool(active_roles & late_roles)


def _legacy_fields_and_defaults(project_root: Path, current_values: dict[str, Any] | None = None) -> tuple[list[FieldMeta], dict[str, Any], list[str]]:
    project_cfg = load_project_config(project_root)
    current = dict(current_values or {})
    defaults = dict(project_cfg.defaults)
    defaults.update({key: value for key, value in current.items() if value not in (None, "")})
    defaults.setdefault("runner", "auto")
    defaults.setdefault("model", "auto")
    defaults.setdefault("effort", "auto")

    all_tags = load_available_tags(project_root)
    selected_tags = [tag for tag in defaults.get("tags", []) if tag in all_tags]
    defaults["tags"] = selected_tags

    fields: list[FieldMeta] = []
    seen: set[str] = set()

    first_role, last_role = _normalize_stage_bounds(
        str(defaults.get("first_role", "")),
        str(defaults.get("last_role", "")),
        list(STAGE_ORDER),
    )
    defaults["first_role"] = first_role
    defaults["last_role"] = last_role
    first_index = STAGE_ORDER.index(first_role) if first_role in STAGE_ORDER else 0
    last_index = STAGE_ORDER.index(last_role) if last_role in STAGE_ORDER else len(STAGE_ORDER) - 1
    active_roles = set(STAGE_ORDER[first_index:last_index + 1])

    _append_field(fields, seen, FieldMeta(key="task_id", label="Task Id", kind=FieldKind.STRING, section="custom"))
    if _legacy_top_level_fields_enabled(active_roles):
        _append_field(
            fields,
            seen,
            FieldMeta(
                key="target_branch",
                label="Target Branch",
                kind=FieldKind.SELECT if project_cfg.available_list("target_branch") else FieldKind.STRING,
                options=project_cfg.available_list("target_branch"),
                default=defaults.get("target_branch", ""),
                section="custom",
            ),
        )
        _append_field(
            fields,
            seen,
            FieldMeta(key="service", label="Service", kind=FieldKind.STRING, default=defaults.get("service", ""), section="custom"),
        )
        _append_field(
            fields,
            seen,
            FieldMeta(
                key="namespace",
                label="Namespace",
                kind=FieldKind.SELECT if project_cfg.available_list("namespace") else FieldKind.STRING,
                options=project_cfg.available_list("namespace"),
                default=defaults.get("namespace", ""),
                section="custom",
            ),
        )
        _append_field(
            fields,
            seen,
            FieldMeta(
                key="tags",
                label="Tags",
                kind=FieldKind.MULTI_SELECT,
                options=sorted(all_tags),
                default=selected_tags,
                section="custom",
            ),
        )

    tag_defs = load_tag_definitions(selected_tags, project_root)
    for _tag_name, param, available, default in collect_params(tag_defs, project_cfg.tag_params, active_roles):
        project_default = defaults.get(param.key)
        if project_default is None and not param.multi and default:
            defaults[param.key] = default
            project_default = default
        _append_field(
            fields,
            seen,
            FieldMeta(
                key=param.key,
                label=_key_to_label(param.key),
                kind=_infer_kind(project_default, available, multi=param.multi),
                required=param.required,
                options=[str(v) for v in available],
                default=project_default if project_default is not None else ([] if param.multi else ""),
                description=param.description,
                section="custom",
            ),
        )

    dynamic_keys = (set(project_cfg.defaults) | set(project_cfg.available)) - seen - _LEGACY_TOP_LEVEL_KEYS
    for key in sorted(dynamic_keys):
        available = [str(v) for v in project_cfg.available_list(key)]
        default = defaults.get(key, [] if available else "")
        _append_field(
            fields,
            seen,
            FieldMeta(
                key=key,
                label=_key_to_label(key),
                kind=_infer_kind(default, available, multi=isinstance(default, list)),
                options=available,
                default=default,
                section="custom",
            ),
        )

    return fields, defaults, list(STAGE_ORDER)


def resolve_legacy_form_state(project_root: Path | None = None, current_values: dict[str, Any] | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    fields, defaults, stages = _legacy_fields_and_defaults(root, current_values)
    return {
        "profile": "",
        "available_profiles": [],
        "available_stages": stages,
        "fields": fields,
        "defaults": defaults,
    }


def load_profile_fields(profile_name: str, project_root: Path | None = None) -> list[FieldMeta]:
    """Build FieldMeta list from profile inputs definition.

    Inputs from pipeline.yml become Custom fields.
    Standard fields (profile, task, runner, first_role, last_role) are excluded.
    """
    root = project_root or Path.cwd()
    pipeline_path = root / ".devpipe" / "profiles" / profile_name / "pipeline.yml"
    if not pipeline_path.exists():
        return []
    data = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}

    inputs = data.get("inputs", {})
    fields: list[FieldMeta] = []
    for name, spec in inputs.items():
        # Skip inputs already handled in the Standard nav section
        if name in _STANDARD_KEYS:
            continue

        input_type = spec.get("type", "string")
        required = spec.get("required", False)
        default = spec.get("default", "")
        options = spec.get("options", [])
        description = spec.get("description", "")

        kind = _type_to_kind(input_type, options)

        fields.append(FieldMeta(
            key=name,
            label=_key_to_label(name),
            kind=kind,
            required=required,
            options=[str(o) for o in options],
            default=default,
            description=description,
            section="custom",
        ))
    return fields


def _type_to_kind(type_str: str, options: list) -> FieldKind:
    """Map pipeline.yml input type to FieldKind."""
    if options:
        return FieldKind.MULTI_SELECT if len(options) > 1 else FieldKind.SELECT
    mapping = {
        "string": FieldKind.STRING,
        "int": FieldKind.INT,
        "integer": FieldKind.INT,
        "array": FieldKind.ARRAY,
        "object": FieldKind.OBJECT,
        "select": FieldKind.SELECT,
        "multi": FieldKind.MULTI_SELECT,
    }
    return mapping.get(type_str, FieldKind.STRING)


def _key_to_label(key: str) -> str:
    """Convert snake_case key to human-readable label."""
    return key.replace("_", " ").title()


def load_default_profile(project_root: Path | None = None) -> str:
    """Read the default profile from .devpipe/config.yaml."""
    root = project_root or Path.cwd()
    config_path = root / ".devpipe" / "config.yaml"
    if not config_path.exists():
        return ""
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return data.get("defaults", {}).get("profile", "")


def prepare_initial_state(project_root: Path | None = None) -> dict[str, Any]:
    """Prepare all data needed for the initial load_defaults action.

    Returns a dict with keys: profile, available_profiles, available_stages,
    fields, defaults.
    """
    root = project_root or Path.cwd()

    profiles = discover_profiles(root)
    default_profile = load_default_profile(root)
    if default_profile not in profiles and profiles:
        default_profile = profiles[0]

    if default_profile:
        fields = load_profile_fields(default_profile, root)
        stages = load_profile_stages(default_profile, root)
        defaults = load_profile_defaults(default_profile, root)
    else:
        legacy_state = resolve_legacy_form_state(root)
        fields = legacy_state["fields"]
        defaults = legacy_state["defaults"]
        stages = legacy_state["available_stages"]

    # Auto-populate task_id from git branch
    branch = _git_branch(root)
    if branch:
        task_id = _task_id_from_branch(branch)
        if task_id:
            defaults.setdefault("task_id", task_id)

    return {
        "profile": default_profile,
        "available_profiles": profiles,
        "available_stages": stages,
        "fields": fields,
        "defaults": defaults,
    }
