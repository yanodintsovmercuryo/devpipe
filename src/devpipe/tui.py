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
from devpipe.project_config import load_project_config
from devpipe.runtime.state import STAGE_ORDER
from devpipe.tags import collect_params, load_available_tags, load_tag_definitions


def _git_branch() -> str:
    try:
        r = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _task_id_from_branch(branch: str) -> str:
    m = re.match(r"^([A-Z]+-[0-9]+)", branch)
    return m.group(1) if m else ""


def _effective_last(cfg: dict) -> str:
    if cfg["last_role"]:
        return cfg["last_role"]
    return "qa_stand" if cfg["target_branch"] else "qa_local"


def _checkbox_with_apply(
    prompt: str, names: list[str], selected: set[str], style, console: Console
) -> list[str] | None:
    """Tag checkbox: Enter toggles, 'Apply' confirms."""
    current = set(selected)
    cursor: str = names[0] if names else "__apply__"
    console.clear()
    while True:
        items = []
        for name in names:
            if name in current:
                title = [("fg:black bg:cyan bold", f" {name} ")]
            else:
                title = [("", f" {name} ")]
            items.append(questionary.Choice(title=title, value=name))
        items.append(Separator())
        items.append(questionary.Choice(title="Apply", value="__apply__"))

        val = questionary.select(prompt, choices=items, style=style, default=cursor).ask()
        console.clear()
        if val is None:
            return None
        if val == "__apply__":
            return [n for n in names if n in current]
        cursor = val
        if val in current:
            current.discard(val)
        else:
            current.add(val)


def _select_or_text(prompt: str, options: list[str], default: str, style) -> str | None:
    if options:
        choices = options + ["(other...)"]
        val = questionary.select(
            prompt, choices=choices,
            default=default if default in options else choices[0],
            style=style,
        ).ask()
        if val is None:
            return None
        if val == "(other...)":
            return questionary.text(prompt, default=default, style=style).ask()
        return val
    return questionary.text(prompt, default=default, style=style).ask()


def _render_summary(cfg: dict, tag_params_meta: list, console: Console) -> None:
    eff_first = cfg["first_role"] or "architect"
    eff_last = _effective_last(cfg)

    table = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
    table.add_column(style="bold dim", width=16)
    table.add_column()

    table.add_row("task", cfg["task"] if cfg["task"] else Text("(empty)  ← required", style="red"))
    table.add_row("task-id", cfg["task_id"] if cfg["task_id"] else Text("none — Jira skipped", style="dim"))
    table.add_row("runner", cfg["runner"])
    table.add_row(
        "target-branch",
        cfg["target_branch"] if cfg["target_branch"] else Text(f"none → last role: {eff_last}", style="dim"),
    )
    table.add_row("service", cfg["service"])
    table.add_row("namespace", cfg["namespace"] if cfg["namespace"] else Text("auto", style="dim"))
    table.add_row("tags", ", ".join(cfg["tags"]) if cfg["tags"] else Text("none", style="dim"))

    for _tag_name, param, _available, _default in tag_params_meta:
        val = cfg["extra_params"].get(param.key, "")
        label = Text(val if val else "(empty)", style="dim" if not val else "default")
        table.add_row(f"  {param.key}", label)

    table.add_row("roles", f"{eff_first} → {eff_last}")

    console.print(Panel(table, title="[bold blue]devpipe[/bold blue]", border_style="blue", padding=(1, 2)))


_STYLE = questionary.Style([
    ("selected", "fg:cyan bold"),
    ("pointer", "fg:cyan bold"),
    ("highlighted", "fg:cyan noreverse"),
    ("answer", "fg:green bold"),
    ("question", "bold"),
])


def run_tui(base_dir: Path) -> RunConfig | None:
    console = Console()
    project_cfg = load_project_config()
    all_tags = load_available_tags()
    available_tag_names = list(all_tags.keys())

    default_tags = [t for t in project_cfg.default("tags", []) if t in all_tags]

    cfg: dict = {
        "task": "",
        "task_id": _task_id_from_branch(_git_branch()),
        "runner": project_cfg.default("runner", "codex"),
        "target_branch": project_cfg.default("target_branch", ""),
        "service": project_cfg.default("service", "acquiring"),
        "namespace": project_cfg.default("namespace", ""),
        "tags": default_tags,
        "extra_params": {},
        "first_role": "",
        "last_role": "",
    }

    def _load_tag_params() -> list:
        eff_first = cfg["first_role"] or "architect"
        eff_last = _effective_last(cfg)
        first_idx = STAGE_ORDER.index(eff_first)
        last_idx = STAGE_ORDER.index(eff_last)
        active_roles = set(STAGE_ORDER[first_idx: last_idx + 1])
        tag_defs = load_tag_definitions(cfg["tags"])
        return collect_params(tag_defs, project_cfg.tag_params, active_roles)

    def _init_tag_param_defaults(tag_params_meta: list) -> None:
        for _tag_name, param, _available, default in tag_params_meta:
            if param.key not in cfg["extra_params"]:
                cfg["extra_params"][param.key] = default

    # Init defaults from already-selected tags
    tag_params_meta = _load_tag_params()
    _init_tag_param_defaults(tag_params_meta)

    while True:
        tag_params_meta = _load_tag_params()
        console.clear()
        _render_summary(cfg, tag_params_meta, console)

        choices: list = [
            "Set task",
            "Set task ID",
            "Set runner",
            "Set target branch",
            "Set service",
            "Set namespace",
        ]
        if available_tag_names:
            choices.append("Set tags")
        for _tag_name, param, _available, _default in tag_params_meta:
            choices.append(f"Set {param.key}")
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
            prev_tags = set(cfg["tags"])
            safe_selected = {t for t in cfg["tags"] if t in available_tag_names}
            val = _checkbox_with_apply("Tags:", available_tag_names, safe_selected, _STYLE, console)
            if val is not None:
                cfg["tags"] = val
                # Init defaults for newly added tags
                new_meta = _load_tag_params()
                _init_tag_param_defaults(new_meta)
                # Clean up params from removed tags
                removed = prev_tags - set(val)
                if removed:
                    removed_defs = load_tag_definitions(list(removed))
                    removed_keys = {p.key for d in removed_defs.values() for p in d.all_params}
                    for k in removed_keys:
                        cfg["extra_params"].pop(k, None)

        elif choice.startswith("Set ") and any(choice == f"Set {p.key}" for _, p, _, _ in tag_params_meta):
            param_key = choice[4:]
            meta = next(((t, p, av, df) for t, p, av, df in tag_params_meta if p.key == param_key), None)
            if meta:
                _tag_name, param, available, default = meta
                current = cfg["extra_params"].get(param.key, default)
                label = f"{param.key}" + (f" — {param.description}" if param.description else "") + ":"
                val = _select_or_text(label, available, current, _STYLE)
                if val is not None:
                    cfg["extra_params"][param.key] = val.strip()

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
                namespace=cfg["namespace"] or None,
                service=cfg["service"] or None,
                tags=cfg["tags"] or [],
                extra_params=cfg["extra_params"] or None,
                first_role=cfg["first_role"] or None,
                last_role=_effective_last(cfg),
            )
