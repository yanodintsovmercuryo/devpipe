from __future__ import annotations

import re
import subprocess
from pathlib import Path

import questionary
from questionary import Separator
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from devpipe.app import RunConfig
from devpipe.project_config import ProjectConfig, load_project_config
from devpipe.runtime.state import STAGE_ORDER


def _git_branch() -> str:
    try:
        r = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _task_id_from_branch(branch: str) -> str:
    m = re.match(r"^([A-Z]+-[0-9]+)", branch)
    return m.group(1) if m else ""


def _available_tags(base_dir: Path) -> list[str]:
    tags_dir = base_dir / "tags"
    if not tags_dir.exists():
        return []
    return sorted(p.name for p in tags_dir.iterdir() if p.is_dir())


def _effective_last(cfg: dict) -> str:
    if cfg["last_role"]:
        return cfg["last_role"]
    return "qa_stand" if cfg["target_branch"] else "qa_local"


def _select_or_text(prompt: str, options: list[str], default: str, style) -> str | None:
    """Show a select list if options are available, otherwise free-text input."""
    if options:
        choices = options + (["(other...)"] if True else [])
        val = questionary.select(prompt, choices=choices, default=default if default in choices else choices[0], style=style).ask()
        if val is None:
            return None
        if val == "(other...)":
            return questionary.text(prompt, default=default, style=style).ask()
        return val
    return questionary.text(prompt, default=default, style=style).ask()


def _render_summary(cfg: dict, console: Console) -> None:
    eff_first = cfg["first_role"] or "architect"
    eff_last = _effective_last(cfg)

    table = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
    table.add_column(style="bold dim", width=16)
    table.add_column()

    table.add_row("task", cfg["task"] if cfg["task"] else Text("(empty)  ← required", style="red"))
    table.add_row("task-id", cfg["task_id"] if cfg["task_id"] else Text("none — Jira skipped", style="dim"))
    table.add_row("runner", cfg["runner"])
    table.add_row("target-branch", cfg["target_branch"] if cfg["target_branch"] else Text(f"none → last role: {eff_last}", style="dim"))
    table.add_row("dataset", cfg["dataset"] if cfg["dataset"] else Text("none", style="dim"))
    table.add_row("service", cfg["service"])
    table.add_row("namespace", cfg["namespace"] if cfg["namespace"] else Text("auto", style="dim"))
    table.add_row("tags", ", ".join(cfg["tags"]) if cfg["tags"] else Text("none", style="dim"))
    table.add_row("roles", f"{eff_first} → {eff_last}")

    console.print(Panel(table, title="[bold blue]devpipe[/bold blue]", border_style="blue", padding=(1, 2)))


_STYLE = questionary.Style([
    ("selected", "fg:cyan bold"),
    ("pointer", "fg:cyan bold"),
    ("highlighted", "fg:cyan"),
    ("answer", "fg:green bold"),
    ("question", "bold"),
])


def run_tui(base_dir: Path) -> RunConfig | None:
    console = Console()
    project_cfg = load_project_config()
    available_tags = _available_tags(base_dir)

    cfg: dict = {
        "task": "",
        "task_id": _task_id_from_branch(_git_branch()),
        "runner": project_cfg.default("runner", "codex"),
        "target_branch": project_cfg.default("target_branch", ""),
        "dataset": project_cfg.default("dataset", ""),
        "service": project_cfg.default("service", "acquiring"),
        "namespace": project_cfg.default("namespace", ""),
        "tags": list(project_cfg.default("tags", [])),
        "first_role": "",
        "last_role": "",
    }

    while True:
        console.clear()
        _render_summary(cfg, console)

        choices: list = [
            "Set task",
            "Set task ID",
            "Set runner",
            "Set target branch",
            "Set dataset",
            "Set service",
            "Set namespace",
        ]
        if available_tags:
            choices.append("Set tags")
        choices.extend(["Set first role", "Set last role"])
        if cfg["task"]:
            choices.extend([Separator(), "▶  Run"])

        choice = questionary.select("", choices=choices, style=_STYLE, use_shortcuts=False).ask()
        if choice is None:
            return None

        if choice == "Set task":
            val = questionary.text("Task:", default=cfg["task"], style=_STYLE).ask()
            if val is not None:
                cfg["task"] = val.strip()

        elif choice == "Set task ID":
            val = questionary.text("Task ID (empty to skip Jira):", default=cfg["task_id"], style=_STYLE).ask()
            if val is not None:
                cfg["task_id"] = val.strip()

        elif choice == "Set runner":
            val = questionary.select("Runner:", choices=["codex", "claude"], default=cfg["runner"], style=_STYLE).ask()
            if val is not None:
                cfg["runner"] = val

        elif choice == "Set target branch":
            val = _select_or_text(
                "Target branch:",
                project_cfg.available_list("target_branch"),
                cfg["target_branch"],
                _STYLE,
            )
            if val is not None:
                cfg["target_branch"] = val.strip()

        elif choice == "Set dataset":
            val = _select_or_text(
                "Dataset:",
                project_cfg.available_list("dataset"),
                cfg["dataset"],
                _STYLE,
            )
            if val is not None:
                cfg["dataset"] = val.strip()

        elif choice == "Set service":
            val = questionary.text("Service:", default=cfg["service"], style=_STYLE).ask()
            if val is not None:
                cfg["service"] = val.strip()

        elif choice == "Set namespace":
            val = _select_or_text(
                "Namespace (empty for auto):",
                project_cfg.available_list("namespace"),
                cfg["namespace"],
                _STYLE,
            )
            if val is not None:
                cfg["namespace"] = val.strip()

        elif choice == "Set tags":
            val = questionary.checkbox("Tags:", choices=available_tags, default=cfg["tags"], style=_STYLE).ask()
            if val is not None:
                cfg["tags"] = val

        elif choice == "Set first role":
            eff_last = _effective_last(cfg)
            last_idx = STAGE_ORDER.index(eff_last)
            allowed = STAGE_ORDER[: last_idx + 1]
            current = cfg["first_role"] or "architect"
            val = questionary.select(
                "First role:", choices=allowed,
                default=current if current in allowed else allowed[0], style=_STYLE,
            ).ask()
            if val is not None:
                cfg["first_role"] = "" if val == "architect" else val

        elif choice == "Set last role":
            eff_first = cfg["first_role"] or "architect"
            first_idx = STAGE_ORDER.index(eff_first)
            allowed = STAGE_ORDER[first_idx:]
            current = cfg["last_role"] or _effective_last(cfg)
            val = questionary.select(
                "Last role:", choices=allowed,
                default=current if current in allowed else allowed[-1], style=_STYLE,
            ).ask()
            if val is not None:
                cfg["last_role"] = val

        elif choice == "▶  Run":
            return RunConfig(
                task_id=cfg["task_id"] or None,
                task=cfg["task"],
                runner=cfg["runner"],
                target_branch=cfg["target_branch"] or None,
                dataset=cfg["dataset"] or None,
                namespace=cfg["namespace"] or None,
                service=cfg["service"] or None,
                tags=cfg["tags"] or [],
                first_role=cfg["first_role"] or None,
                last_role=_effective_last(cfg),
            )
