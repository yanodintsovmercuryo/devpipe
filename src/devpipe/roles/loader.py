from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from devpipe.runners.profile_map import EFFORT_LEVELS, MODEL_LEVELS

_LEVEL_ALIASES = {
    "medium": "middle",
}


@dataclass
class RoleDefinition:
    name: str
    runner: str
    model: str
    effort: str
    prompt: str
    output_schema: dict[str, object]
    allowed_inputs: list[str]
    produced_outputs: list[str]
    retry_limit: int


def load_roles(roles_dir: str | Path) -> dict[str, RoleDefinition]:
    base = Path(roles_dir)
    roles: dict[str, RoleDefinition] = {}
    for role_dir in sorted(path for path in base.iterdir() if path.is_dir() and not path.name.startswith(".")):
        role_meta = yaml.safe_load((role_dir / "role.yaml").read_text(encoding="utf-8"))
        prompt = (role_dir / "prompt.md").read_text(encoding="utf-8") if (role_dir / "prompt.md").exists() else ""
        schema = json.loads((role_dir / "output.schema.json").read_text(encoding="utf-8")) if (role_dir / "output.schema.json").exists() else {}
        model = _LEVEL_ALIASES.get(role_meta.get("model", "middle"), role_meta.get("model", "middle"))
        effort = _LEVEL_ALIASES.get(role_meta.get("effort", "middle"), role_meta.get("effort", "middle"))
        if model not in MODEL_LEVELS:
            raise ValueError(f"Role '{role_meta['name']}' has unsupported model level '{model}'")
        if effort not in EFFORT_LEVELS:
            raise ValueError(f"Role '{role_meta['name']}' has unsupported effort level '{effort}'")
        runner = role_meta.get("runner", "codex")
        if runner not in {"codex", "claude"}:
            raise ValueError(f"Role '{role_meta['name']}' has unsupported runner '{runner}'")
        definition = RoleDefinition(
            name=role_meta["name"],
            runner=runner,
            model=model,
            effort=effort,
            prompt=prompt,
            output_schema=schema,
            allowed_inputs=list(role_meta.get("allowed_inputs", [])),
            produced_outputs=list(role_meta.get("produces", [])),
            retry_limit=int(role_meta.get("retry_limit", 1)),
        )
        roles[definition.name] = definition
    return roles
