from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import questionary
from questionary import Separator
from questionary.prompts.common import InquirerControl
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_orig_get_choice_tokens = InquirerControl._get_choice_tokens


def _patched_get_choice_tokens(self):  # type: ignore[override]
    tokens = _orig_get_choice_tokens(self)
    result = []
    for s, t in tokens:
        if s == "class:text" and "  Description: " in t:
            t = t.replace("  Description: ", "\n  ", 1)
        elif s == "class:disabled" and t.startswith("- "):
            t = t[2:]
        result.append((s, t))
    return result


InquirerControl._get_choice_tokens = _patched_get_choice_tokens  # type: ignore[method-assign]


from devpipe.app import RunConfig
from devpipe.history import load_history, save_run
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
    prompt: str,
    names: list[str],
    selected: set[str],
    style,
    console: Console,
    render: Callable[[], None] | None = None,
) -> list[str] | None:
    """Tag checkbox: Enter toggles, 'Apply' confirms."""
    current = set(selected)
    cursor: str = names[0] if names else "__apply__"
    while True:
        console.clear()
        if render:
            render()
            print()
        items = []
        for name in names:
            if name in current:
                title = [("fg:black bg:cyan bold", f" {name} ")]
            else:
                title = [("", f" {name} ")]
            items.append(questionary.Choice(title=title, value=name))
        items.append(Separator(" "))
        items.append(questionary.Choice(title="Apply", value="__apply__"))

        val = questionary.select(prompt, choices=items, style=style, default=cursor).ask()
        if val is None:
            return None
        if val == "__apply__":
            return [n for n in names if n in current]
        cursor = val
        if val in current:
            current.discard(val)
        else:
            current.add(val)


def _multi_param_select(
    prompt: str,
    available: list[str],
    current: list[str],
    style,
    console: Console,
    render: Callable[[], None] | None = None,
) -> list[str] | None:
    """Multi-select for params: builtin choices + custom input. Custom values disappear when deselected."""
    builtin = list(available)
    selected: set[str] = set(current)
    # custom values: those selected but not in builtin
    custom: list[str] = [v for v in current if v not in builtin]
    cursor: str = (builtin + custom)[0] if (builtin or custom) else "__apply__"

    while True:
        console.clear()
        if render:
            render()
            print()

        all_choices = builtin + custom
        items = []
        for name in all_choices:
            if name in selected:
                title = [("fg:black bg:cyan bold", f" {name} ")]
            else:
                title = [("", f" {name} ")]
            items.append(questionary.Choice(title=title, value=name))
        items.append(Separator(" "))
        items.append(questionary.Choice(title="Add custom value...", value="__custom__"))
        items.append(questionary.Choice(title="Apply", value="__apply__"))

        val = questionary.select(prompt, choices=items, style=style, default=cursor, qmark="").ask()
        if val is None:
            return None
        if val == "__apply__":
            return [v for v in (builtin + custom) if v in selected]
        if val == "__custom__":
            console.clear()
            if render:
                render()
                print()
            new_val = questionary.text("Custom value:", style=style, qmark="").ask()
            if new_val and new_val.strip():
                v = new_val.strip()
                if v not in builtin and v not in custom:
                    custom.append(v)
                selected.add(v)
                cursor = v
            continue
        cursor = val
        if val in selected:
            selected.discard(val)
            # remove custom value from list when deselected
            if val not in builtin and val in custom:
                custom.remove(val)
                cursor = all_choices[0] if all_choices else "__apply__"
        else:
            selected.add(val)


def _select_or_text(prompt: str, options: list[str], default: str, style) -> str | None:
    if options:
        choices = options + ["(other...)"]
        val = questionary.select(
            prompt, choices=choices,
            default=default if default in options else choices[0],
            style=style, qmark="",
        ).ask()
        if val is None:
            return None
        if val == "(other...)":
            return questionary.text(prompt, default=default, style=style, qmark="").ask()
        return val
    return questionary.text(prompt, default=default, style=style, qmark="").ask()


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
        raw = cfg["extra_params"].get(param.key, "")
        if isinstance(raw, list):
            display = ", ".join(raw) if raw else ""
        else:
            display = raw
        label = Text(display if display else "(empty)", style="dim" if not display else "default")
        table.add_row(f"  {param.key}", label)

    table.add_row("roles", f"{eff_first} → {eff_last}")

    console.print(Panel(table, title="[bold blue]devpipe[/bold blue]", border_style="blue", padding=(1, 2)))


_STYLE = questionary.Style([
    ("selected", "fg:cyan bold"),
    ("pointer", "fg:cyan bold"),
    ("highlighted", "fg:cyan noreverse"),
    ("answer", "fg:green bold"),
    ("question", "bold"),
    ("text", "fg:#888888"),
    ("disabled", "fg:#555555"),
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

    history = load_history()
    if history:
        console.clear()
        h_choices = []
        for i, h in enumerate(history[:10]):
            task_short = (h.get("task") or "")[:48]
            label = f"{h.get('date', '')}  {h.get('task_id') or '—':>10}  {task_short}"
            h_choices.append(questionary.Choice(title=label, value=i))
        h_choices.append(Separator(" "))
        h_choices.append(questionary.Choice(title="Start fresh", value=-1))
        picked = questionary.select(
            "Load from history:", choices=h_choices, style=_STYLE, qmark="",
        ).ask()
        if picked is None:
            return None
        if picked >= 0:
            h = history[picked]
            cfg.update({
                "task":          h.get("task", ""),
                "task_id":       h.get("task_id", "") or _task_id_from_branch(_git_branch()),
                "runner":        h.get("runner", cfg["runner"]),
                "target_branch": h.get("target_branch", ""),
                "service":       h.get("service", cfg["service"]),
                "namespace":     h.get("namespace", ""),
                "tags":          [t for t in (h.get("tags") or []) if t in available_tag_names],
                "extra_params":  dict(h.get("extra_params") or {}),
                "first_role":    h.get("first_role", ""),
                "last_role":     h.get("last_role", ""),
            })

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
                project_default = project_cfg.defaults.get(param.key)
                if project_default is not None:
                    cfg["extra_params"][param.key] = project_default
                else:
                    cfg["extra_params"][param.key] = [] if param.multi else default

    def _input_header() -> None:
        console.clear()
        _render_summary(cfg, tag_params_meta, console)
        print()

    # Pre-populate extra_params from project_cfg.defaults (all tag params, no role filter)
    _STANDARD_KEYS = {"task", "task_id", "runner", "target_branch", "service", "namespace", "tags", "first_role", "last_role"}
    for key, val in project_cfg.defaults.items():
        if key not in _STANDARD_KEYS:
            if isinstance(val, list):
                val = [str(v) for v in val]
            elif val is not None:
                val = str(val)
            cfg["extra_params"].setdefault(key, val)

    # Init defaults from already-selected tags
    tag_params_meta = _load_tag_params()
    _init_tag_param_defaults(tag_params_meta)

    while True:
        tag_params_meta = _load_tag_params()
        console.clear()
        _render_summary(cfg, tag_params_meta, console)
        print()

        def _c(title: str, desc: str) -> questionary.Choice:
            return questionary.Choice(title, description="\n\n  " + desc)

        choices: list = [
            _c("Set task",          "What needs to be done — the main prompt for the AI agent"),
            _c("Set task ID",       "Jira ticket ID (e.g. MRC-123); leave empty to skip Jira context"),
            _c("Set runner",        "AI runner: codex (OpenAI Codex CLI) or claude (Claude Code)"),
            _c("Set target branch", "Deploy stand branch; if empty — pipeline stops at qa_local"),
            _c("Set service",       "Service name used for namespace lookup and release context"),
            _c("Set namespace",     "Kubernetes namespace override; auto-resolved from service+branch if empty"),
        ]
        if available_tag_names:
            choices.append(_c("Set tags", "Active tag set — each tag injects rules and params into the pipeline"))
        for _tag_name, param, _available, _default in tag_params_meta:
            desc = param.description or f"Parameter for {_tag_name} tag"
            choices.append(_c(f"Set {param.key}", desc))
        choices.append(_c("Set first role", "First pipeline stage to run (default: architect)"))
        choices.append(_c("Set last role",  "Last pipeline stage to run (default: qa_stand if target branch set, else qa_local)"))
        choices.append(Separator(" "))
        run_desc = "\n\n  Start the pipeline with current configuration" if cfg["task"] else "\n\n  Task is required — use Set task first"
        choices.append(questionary.Choice("▶ Run", description=run_desc))

        choice = questionary.select("", choices=choices, style=_STYLE, use_shortcuts=False, qmark="").ask()
        if choice is None:
            return None

        if choice == "Set task":
            _input_header()
            val = questionary.text("Task:", default=cfg["task"], style=_STYLE, qmark="").ask()
            if val is not None:
                cfg["task"] = val.strip()

        elif choice == "Set task ID":
            _input_header()
            val = questionary.text("Task ID (empty to skip Jira):", default=cfg["task_id"], style=_STYLE, qmark="").ask()
            if val is not None:
                cfg["task_id"] = val.strip()

        elif choice == "Set runner":
            _input_header()
            val = questionary.select("Runner:", choices=["codex", "claude"], default=cfg["runner"], style=_STYLE, qmark="").ask()
            if val is not None:
                cfg["runner"] = val

        elif choice == "Set target branch":
            _input_header()
            val = _select_or_text(
                "Target branch:",
                project_cfg.available_list("target_branch"),
                cfg["target_branch"],
                _STYLE,
            )
            if val is not None:
                cfg["target_branch"] = val.strip()

        elif choice == "Set service":
            _input_header()
            val = questionary.text("Service:", default=cfg["service"], style=_STYLE, qmark="").ask()
            if val is not None:
                cfg["service"] = val.strip()

        elif choice == "Set namespace":
            _input_header()
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
            val = _checkbox_with_apply(
                "Tags:", available_tag_names, safe_selected, _STYLE, console,
                render=lambda: _render_summary(cfg, tag_params_meta, console),
            )
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
                label = f"{param.key}" + (f" — {param.description}" if param.description else "") + ":"
                if param.multi:
                    raw = cfg["extra_params"].get(param.key, [])
                    cur_list = raw if isinstance(raw, list) else ([raw] if raw else [])
                    val_list = _multi_param_select(
                        label, available, cur_list, _STYLE, console,
                        render=lambda: _render_summary(cfg, tag_params_meta, console),
                    )
                    if val_list is not None:
                        cfg["extra_params"][param.key] = val_list
                else:
                    _input_header()
                    current = cfg["extra_params"].get(param.key, default)
                    val = _select_or_text(label, available, current if isinstance(current, str) else default, _STYLE)
                    if val is not None:
                        cfg["extra_params"][param.key] = val.strip()

        elif choice == "Set first role":
            _input_header()
            eff_last = _effective_last(cfg)
            last_idx = STAGE_ORDER.index(eff_last)
            allowed = STAGE_ORDER[: last_idx + 1]
            current = cfg["first_role"] or "architect"
            val = questionary.select(
                "First role:", choices=allowed,
                default=current if current in allowed else allowed[0], style=_STYLE, qmark="",
            ).ask()
            if val is not None:
                cfg["first_role"] = "" if val == "architect" else val

        elif choice == "Set last role":
            _input_header()
            eff_first = cfg["first_role"] or "architect"
            first_idx = STAGE_ORDER.index(eff_first)
            allowed = STAGE_ORDER[first_idx:]
            current = cfg["last_role"] or _effective_last(cfg)
            val = questionary.select(
                "Last role:", choices=allowed,
                default=current if current in allowed else allowed[-1], style=_STYLE, qmark="",
            ).ask()
            if val is not None:
                cfg["last_role"] = val

        elif choice == "▶ Run":
            if not cfg["task"]:
                continue
            save_run({**cfg, "last_role": _effective_last(cfg)})
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
