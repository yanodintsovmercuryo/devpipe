from __future__ import annotations

from pathlib import Path

import yaml


class ConfigStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        return yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}

