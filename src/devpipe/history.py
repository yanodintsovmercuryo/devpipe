from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from devpipe.app import RunConfig
    from devpipe.runtime.state import PipelineState

HISTORY_DIR = Path.home() / ".devpipecfg" / "history"
MAX_ENTRIES_PER_PROFILE = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _get_history_path(profile: str | None) -> Path:
    """Get history file path for a given profile."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    profile_name = profile or "default"
    # Sanitize profile name for filename
    safe_name = profile_name.replace("/", "_").replace("\\", "_")
    return HISTORY_DIR / f"{safe_name}.yaml"


def save_run(config: RunConfig, state: "PipelineState | None" = None) -> None:
    """Save or update a run entry in profile-scoped history file."""
    history_path = _get_history_path(config.profile)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    if history_path.exists():
        entries = yaml.safe_load(history_path.read_text(encoding="utf-8")) or []

    # Determine if we're updating an existing entry
    run_id = state.run_id if state else None
    existing_index = -1
    if run_id:
        for idx, entry in enumerate(entries):
            if entry.get("run_id") == run_id:
                existing_index = idx
                break

    extra: Any = config.extra_params or {}
    entry: dict[str, Any] = {
        "profile": config.profile or "default",
        "run_id": run_id or "",
        "date": _now_iso(),
        "task": config.task or "",
        "task_id": config.task_id or "",
        "runner": config.runner or "codex",
        "model": config.model or "auto",
        "effort": config.effort or "auto",
        "target_branch": config.target_branch or "",
        "service": config.service or "",
        "namespace": config.namespace or "",
        "tags": list(config.tags or []),
        "extra_params": dict(extra),
        "first_role": config.first_role or "",
        "last_role": config.last_role or "",
    }

    # Set status from state if available, otherwise default to running
    if state and hasattr(state, "status"):
        entry["status"] = state.status
    else:
        entry["status"] = "running"

    # Include stage attempts if state available
    if state and hasattr(state, "stage_attempts") and state.stage_attempts:
        entry["attempts"] = [
            {
                "stage": att.get("stage"),
                "attempt_number": att.get("attempt_number"),
                "in_snapshot": att.get("in_snapshot", {}),
                "out_snapshot": att.get("out_snapshot", {}),
                "selected_rule": att.get("selected_rule"),
                "next_stage": att.get("next_stage"),
            }
            for att in state.stage_attempts
        ]

    if existing_index >= 0:
        # Update existing entry, preserving original date and finished_at
        old_entry = entries[existing_index]
        entry["date"] = old_entry.get("date", entry["date"])
        # Keep existing finished_at if present; will set below if needed
        if "finished_at" in old_entry:
            entry["finished_at"] = old_entry["finished_at"]
        entries[existing_index] = entry
    else:
        entries.insert(0, entry)

    # If status indicates completion and no finished_at, set it now
    final_states = {"completed", "failed", "cancelled"}
    if entry.get("status") in final_states and not entry.get("finished_at"):
        entry["finished_at"] = _now_iso()

    # Trim to max per profile
    trimmed = entries[:MAX_ENTRIES_PER_PROFILE]
    if len(entries) > len(trimmed):
        entries = trimmed
    else:
        entries = trimmed

    history_path.write_text(
        yaml.dump(entries, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def finish_run(config: RunConfig) -> None:
    """Mark the most recent matching run as finished."""
    history_path = _get_history_path(config.profile)
    if not history_path.exists():
        return

    entries = yaml.safe_load(history_path.read_text(encoding="utf-8")) or []
    updated = False
    for entry in entries:
        if entry.get("finished_at"):
            continue
        if entry.get("task", "") != (config.task or ""):
            continue
        if entry.get("task_id", "") != (config.task_id or ""):
            continue
        entry["finished_at"] = _now_iso()
        entry["status"] = entry.get("status", "completed")  # Keep final status
        updated = True
        break

    if updated:
        history_path.write_text(
            yaml.dump(entries[:MAX_ENTRIES_PER_PROFILE], allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


def load_history(profile: str | None = None) -> list[dict]:
    """Load run history for a specific profile (or all if None)."""
    if profile is None:
        # Load from all profiles by merging (reverse chronological across all)
        all_entries: list[dict] = []
        if HISTORY_DIR.exists():
            for hist_file in HISTORY_DIR.iterdir():
                if hist_file.suffix == ".yaml":
                    try:
                        entries = yaml.safe_load(hist_file.read_text(encoding="utf-8")) or []
                        all_entries.extend(entries)
                    except Exception:
                        continue
        # Sort by date descending (newest first)
        all_entries.sort(key=lambda e: e.get("date", ""), reverse=True)
        return all_entries[:MAX_ENTRIES_PER_PROFILE]

    history_path = _get_history_path(profile)
    if not history_path.exists():
        return []
    return yaml.safe_load(history_path.read_text(encoding="utf-8")) or []


def get_run_by_id(run_id: str, profile: str | None = None) -> dict | None:
    """Find a specific run by run_id in history."""
    history_path = _get_history_path(profile)
    if not history_path.exists():
        return None
    entries = yaml.safe_load(history_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        if entry.get("run_id") == run_id:
            return entry
    return None
