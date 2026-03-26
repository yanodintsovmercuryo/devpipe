from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

BUILTIN_TAGS_DIR = Path(__file__).resolve().parents[3] / "tags"


@dataclass
class TagParam:
    key: str
    description: str = ""
    required: bool = False
    available: list[str] = field(default_factory=list)


@dataclass
class TagDefinition:
    name: str
    description: str = ""
    params: list[TagParam] = field(default_factory=list)

    def param(self, key: str) -> TagParam | None:
        return next((p for p in self.params if p.key == key), None)


def load_tag_definition(tag_name: str, tags_dir: Path = BUILTIN_TAGS_DIR) -> TagDefinition | None:
    tag_yaml = tags_dir / tag_name / "tag.yaml"
    if not tag_yaml.exists():
        return None
    data = yaml.safe_load(tag_yaml.read_text(encoding="utf-8")) or {}
    params = [
        TagParam(
            key=p["key"],
            description=p.get("description", ""),
            required=p.get("required", False),
            available=p.get("available", []),
        )
        for p in data.get("params", [])
    ]
    return TagDefinition(
        name=tag_name,
        description=data.get("description", ""),
        params=params,
    )


def load_tag_definitions(tag_names: list[str], tags_dir: Path = BUILTIN_TAGS_DIR) -> dict[str, TagDefinition]:
    result = {}
    for name in tag_names:
        defn = load_tag_definition(name, tags_dir)
        if defn:
            result[name] = defn
    return result


def collect_params(
    tag_definitions: dict[str, TagDefinition],
    project_tag_params: dict[str, dict],
) -> list[tuple[str, TagParam, list[str], str]]:
    """Returns list of (tag_name, param, available_values, default_value)."""
    seen: set[str] = set()
    result = []
    for tag_name, defn in tag_definitions.items():
        overrides = project_tag_params.get(tag_name, {})
        for param in defn.params:
            if param.key in seen:
                continue
            seen.add(param.key)
            available = overrides.get("available", {}).get(param.key, param.available)
            default = str(overrides.get("defaults", {}).get(param.key, available[0] if available else ""))
            result.append((tag_name, param, available, default))
    return result
