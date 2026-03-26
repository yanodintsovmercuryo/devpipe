from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ProjectConfig:
    defaults: dict = field(default_factory=dict)
    available: dict = field(default_factory=dict)

    def default(self, key: str, fallback=None):
        return self.defaults.get(key, fallback)

    def available_list(self, key: str) -> list[str]:
        return self.available.get(key, [])


def load_project_config(cwd: Path | None = None) -> ProjectConfig:
    path = (cwd or Path.cwd()) / ".devpipe" / "config.yaml"
    if not path.exists():
        return ProjectConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ProjectConfig(
        defaults=data.get("defaults", {}),
        available=data.get("available", {}),
    )
