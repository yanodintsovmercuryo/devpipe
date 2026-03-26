from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

BUILTIN_TAGS_DIR = Path(__file__).resolve().parents[3] / "tags"

PARAMS_FILE_NAMES = {
    "architect": "ARCHITECT_PARAMS.yaml",
    "developer": "DEVELOPER_PARAMS.yaml",
    "test_developer": "TEST_DEVELOPER_PARAMS.yaml",
    "qa_local": "QA_LOCAL_PARAMS.yaml",
    "release": "RELEASE_PARAMS.yaml",
    "qa_stand": "QA_STAND_PARAMS.yaml",
}


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
    params_by_role: dict[str, list[TagParam]] = field(default_factory=dict)

    @property
    def all_params(self) -> list[TagParam]:
        seen: set[str] = set()
        result = []
        for params in self.params_by_role.values():
            for p in params:
                if p.key not in seen:
                    seen.add(p.key)
                    result.append(p)
        return result

    def params_for_role(self, role: str) -> list[TagParam]:
        return self.params_by_role.get(role, [])


def _load_params_file(path: Path) -> list[TagParam]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        TagParam(
            key=p["key"],
            description=p.get("description", ""),
            required=p.get("required", False),
            available=p.get("available", []),
        )
        for p in data.get("params", [])
    ]


def load_tag_definition(tag_name: str, tags_dir: Path = BUILTIN_TAGS_DIR) -> TagDefinition | None:
    tag_dir = tags_dir / tag_name
    if not tag_dir.exists():
        return None

    description = ""
    tag_yaml = tag_dir / "tag.yaml"
    if tag_yaml.exists():
        data = yaml.safe_load(tag_yaml.read_text(encoding="utf-8")) or {}
        description = data.get("description", "")

    params_by_role = {}
    for role, filename in PARAMS_FILE_NAMES.items():
        params = _load_params_file(tag_dir / filename)
        if params:
            params_by_role[role] = params

    return TagDefinition(name=tag_name, description=description, params_by_role=params_by_role)


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
        for param in defn.all_params:
            if param.key in seen:
                continue
            seen.add(param.key)
            available = overrides.get("available", {}).get(param.key, param.available)
            default = str(overrides.get("defaults", {}).get(param.key, available[0] if available else ""))
            result.append((tag_name, param, available, default))
    return result
