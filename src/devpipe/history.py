from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from devpipe.app import RunConfig

HISTORY_PATH = Path.home() / ".devpipecfg" / "history.yaml"
MAX_ENTRIES = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def save_run(config: RunConfig) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    if HISTORY_PATH.exists():
        entries = yaml.safe_load(HISTORY_PATH.read_text(encoding="utf-8")) or []

    extra: Any = config.extra_params or {}
    entry: dict[str, Any] = {
        "date": _now_iso(),
        "task": config.task or "",
        "task_id": config.task_id or "",
        "runner": config.runner or "codex",
        "target_branch": config.target_branch or "",
        "service": config.service or "",
        "namespace": config.namespace or "",
        "tags": list(config.tags or []),
        "extra_params": dict(extra),
        "first_role": config.first_role or "",
        "last_role": config.last_role or "",
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
