"""Declarative binding resolution for stage inputs."""
from __future__ import annotations

from typing import Any


class BindingError(Exception):
    """Error resolving a binding."""
    pass


def resolve_bindings(bindings: dict[str, str], context: dict[str, Any]) -> dict[str, Any]:
    resolved = {}
    for target, source_path in bindings.items():
        try:
            resolved[target] = resolve_source(source_path, context)
        except BindingError as e:
            raise BindingError(f"Failed to resolve binding '{target}' from '{source_path}': {e}") from e
    return resolved


def _lookup_path(root: dict[str, Any], path: str) -> Any:
    """Traverse nested dict using dot-separated path; return None if any segment missing."""
    parts = path.split(".")
    value: Any = root
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value


def resolve_source(path: str, context: dict[str, Any]) -> Any:
    # out.<field> - current stage output
    if path.startswith("out."):
        if "_current_stage" not in context:
            raise BindingError("cannot resolve out.* without _current_stage in context")
        field_name = path[4:]
        stage_name = context["_current_stage"]
        stage_outputs = context["stages"].get(stage_name, {})
        return stage_outputs.get(field_name)

    # input.<key> or in.<key>
    if path.startswith("input.") or path.startswith("in."):
        key = path.split(".", 1)[1]
        return context["inputs"].get(key)

    # stage.<stage>.[out.]<field>
    if path.startswith("stage."):
        parts = path.split(".")
        if len(parts) < 3:
            raise BindingError(f"invalid stage path: {path}")
        stage_name = parts[1]
        remainder = ".".join(parts[2:])
        if remainder.startswith("out."):
            field_name = remainder[4:]
        else:
            field_name = remainder
        stage_outputs = context["stages"].get(stage_name, {})
        return stage_outputs.get(field_name)

    # context.<nested.path>
    if path.startswith("context."):
        subpath = path[8:]
        ctx = context.get("context", {})
        return _lookup_path(ctx, subpath) if subpath else ctx

    # runtime.<nested.path>
    if path.startswith("runtime."):
        subpath = path[8:]
        rt = context.get("runtime", {})
        return _lookup_path(rt, subpath) if subpath else rt

    # integration.<nested.path>
    if path.startswith("integration."):
        subpath = path[12:]
        integration = context.get("integration", {})
        return _lookup_path(integration, subpath) if subpath else integration

    raise BindingError(f"unsupported source path: {path}")
