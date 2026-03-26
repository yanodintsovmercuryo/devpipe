from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

HISTORY_PATH = Path.home() / ".devpipecfg" / "history.yaml"
MAX_ENTRIES = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def save_run(cfg: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    if HISTORY_PATH.exists():
        entries = yaml.safe_load(HISTORY_PATH.read_text(encoding="utf-8")) or []

    entry: dict[str, Any] = {
        "date": _now_iso(),
        "task": cfg.get("task", ""),
        "task_id": cfg.get("task_id", ""),
        "runner": cfg.get("runner", "codex"),
        "target_branch": cfg.get("target_branch", ""),
        "service": cfg.get("service", ""),
        "namespace": cfg.get("namespace", ""),
        "tags": list(cfg.get("tags", [])),
        "extra_params": dict(cfg.get("extra_params", {})),
        "first_role": cfg.get("first_role", ""),
        "last_role": cfg.get("last_role", ""),
    }
    entries.insert(0, entry)
    HISTORY_PATH.write_text(
        yaml.dump(entries[:MAX_ENTRIES], allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def load_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    return yaml.safe_load(HISTORY_PATH.read_text(encoding="utf-8")) or []
