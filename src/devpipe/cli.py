from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from devpipe.app import RunConfig, build_default_app
from devpipe.roles.loader import load_roles
from devpipe.runtime.state import STAGE_ORDER

# Partial ESC at end of chunk — carry to next chunk
_PARTIAL_ESC = re.compile(r"\x1b(?:\[[\x20-\x3f]*)?$")
# Panel: blank + border + content + border = 4 lines; +1 blank after = 5
_PANEL_LINES = 5
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _parse_chunk(text: str) -> tuple[list[str], str]:
    """Parse a chunk of PTY output into finished lines and the current partial line.

    Rules:
    - \\r  resets the current line to empty (carriage-return overwrites)
    - \\n  commits the current line and starts a new one
    - ESC sequences ending in 'm' (SGR colors) are kept verbatim
    - All other ESC/control sequences are discarded
    Returns (finished_lines, current_partial).
    """
    lines: list[str] = []
    cur = ""
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\n":
            lines.append(cur)
            cur = ""
            i += 1
        elif c == "\r":
            if i + 1 < len(text) and text[i + 1] == "\n":
                lines.append(cur)  # \r\n = Windows newline — commit line
                cur = ""
                i += 2
            else:
                cur = ""   # bare \r = overwrite from column 0 — discard
                i += 1
        elif c == "\x1b":
            j = i + 1
            if j < len(text) and text[j] == "[":
                # CSI sequence
                j += 1
                while j < len(text) and text[j] in "0123456789;:?>=<!":
                    j += 1
                if j < len(text):
                    cmd = text[j]
                    j += 1
                    if cmd == "m":          # SGR — keep color/style
                        cur += text[i:j]
                    elif cmd in ("H", "f", "G", "A", "B", "C", "D", "E", "F", "J", "d"):
                        cur = ""            # cursor movement → discard partial line
                    # else: other sequences — discard
            elif j < len(text) and text[j] == "]":
                # OSC — skip until BEL or ESC
                j += 1
                while j < len(text) and text[j] not in ("\x07", "\x1b"):
                    j += 1
                if j < len(text):
                    j += 1  # consume BEL or ESC
            else:
                j = min(j + 1, len(text))  # skip 2-char ESC
            i = j
        elif ord(c) < 0x20 or c == "\x7f":
            i += 1  # discard other control chars
        else:
            cur += c
            i += 1
    return lines, cur


class _RunProgress:
    def __init__(self, stages: list[str], console: Console) -> None:
        self.stages = stages
        self.current_stage = ""
        self._console = console
        self._printed_stage: str | None = None
        self._buf: list[str] = []   # colored lines, ready to display
        self._carry = ""            # incomplete ESC from previous chunk
        self._current_line = ""     # partial line (no \n yet)
        self._tick = 0
        self._drawn_n = 0
        self._area_drawn = False

    # ── stage header ─────────────────────────────────────────────────────────

    def set_stage(self, stage: str) -> None:
        self.current_stage = stage
        if stage == self._printed_stage:
            return
        self._printed_stage = stage
        self._buf = []
        self._carry = ""
        self._current_line = ""
        self._tick = 0
        self._area_drawn = False

        idx = self.stages.index(stage) if stage in self.stages else -1
        parts: list[str] = []
        for i, s in enumerate(self.stages):
            if i < idx:
                parts.append(f"[dim green]{s}[/dim green]")
            elif s == stage:
                parts.append(f"[bold cyan]{s}[/bold cyan]")
            else:
                parts.append(f"[dim]{s}[/dim]")
        self._console.print()
        self._console.print(Panel(
            Text.from_markup("  ".join(parts)),
            border_style="blue",
            title="[bold blue]devpipe[/bold blue]",
        ))
        self._console.file.flush()
        self._draw()

    # ── output streaming ─────────────────────────────────────────────────────

    def on_output(self, text: str) -> None:
        text = self._carry + text
        m = _PARTIAL_ESC.search(text)
        if m:
            self._carry = m.group()
            text = text[: m.start()]
        else:
            self._carry = ""

        finished, self._current_line = _parse_chunk(self._current_line + text)
        self._buf.extend(line for line in finished if line.strip())
        self._tick += 1
        self._draw()

    # ── in-place window ───────────────────────────────────────────────────────

    def _draw(self) -> None:
        n = max(1, shutil.get_terminal_size().lines - _PANEL_LINES - 1)
        w = max(shutil.get_terminal_size().columns - 4, 20)

        if self._area_drawn:
            sys.stdout.write(f"\x1b[{self._drawn_n + 1}A")

        spinner = _SPINNER[self._tick % len(_SPINNER)]
        sys.stdout.write(f"\x1b[2K\r  {spinner}  \x1b[2m{self.current_stage}\x1b[0m\n")

        display = self._buf + ([self._current_line] if self._current_line.strip() else [])
        trimmed = display[-n:]  # last N lines (newest)
        visible = trimmed + [""] * (n - len(trimmed))  # pad to N with blanks at end
        for line in visible:
            # Truncate visible width (strip SGR for measuring, keep for display)
            plain = re.sub(r"\x1b\[[0-9;]*m", "", line)
            if len(plain) > w:
                # Hard-truncate by visible chars — simple approximation
                line = plain[: w - 1] + "…"
            sys.stdout.write(f"\x1b[2K\r{line}\n")

        sys.stdout.write("\x1b[0m")  # reset any unclosed color codes
        sys.stdout.flush()
        self._area_drawn = True
        self._drawn_n = n


class CommaSeparatedTags(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        current = list(getattr(namespace, self.dest, []) or [])
        for part in values.split(","):
            tag = part.strip()
            if tag and tag not in current:
                current.append(tag)
        setattr(namespace, self.dest, current)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devpipe", description="devpipe")
    subparsers = parser.add_subparsers(dest="command", required=False)

    run_parser = subparsers.add_parser("run", help="Run full pipeline")
    run_parser.add_argument("--task-id", default=None)
    run_parser.add_argument("--task", required=True)
    run_parser.add_argument("--runner", required=True, choices=["codex", "claude"])
    run_parser.add_argument("--roles-dir", default=None)
    run_parser.add_argument("--runs-dir", default=None)
    run_parser.add_argument("--target-branch")
    run_parser.add_argument("--param", dest="params", action="append", metavar="KEY=VALUE",
                            help="Extra tag param, e.g. --param dataset=s4-3ds")
    run_parser.add_argument("--namespace")
    run_parser.add_argument("--service", default="acquiring")
    run_parser.add_argument("--tag", dest="tags", action=CommaSeparatedTags, default=[])
    run_parser.add_argument("--first-role", default=None, choices=["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"])
    run_parser.add_argument("--last-role", default=None, choices=["architect", "developer", "test_developer", "qa_local", "release", "qa_stand"])

    inspect_parser = subparsers.add_parser("inspect", help="Inspect available roles")
    inspect_parser.add_argument("--roles-dir", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        from devpipe.tui import run_tui
        base_dir = Path(args.roles_dir).resolve().parents[0] if getattr(args, "roles_dir", None) else Path(__file__).resolve().parents[2]
        config = run_tui(base_dir)
        if config is None:
            return 0
        app = build_default_app(base_dir)

        first = config.first_role or STAGE_ORDER[0]
        last = config.last_role or STAGE_ORDER[-1]
        fi = STAGE_ORDER.index(first) if first in STAGE_ORDER else 0
        li = STAGE_ORDER.index(last) if last in STAGE_ORDER else len(STAGE_ORDER) - 1
        active_stages = STAGE_ORDER[fi: li + 1]

        console = Console()
        console.clear()
        progress = _RunProgress(active_stages, console)
        runner = app.runners[config.runner]
        runner.output_callback = progress.on_output  # type: ignore[union-attr]

        sys.stdout.write("\x1b[?25l")  # hide cursor
        sys.stdout.flush()
        try:
            state = app.run(config, on_stage_start=progress.set_stage)
        except KeyboardInterrupt:
            sys.stdout.write("\x1b[?25h\n")
            sys.stdout.flush()
            console.print("[dim]interrupted[/dim]")
            return 130
        finally:
            sys.stdout.write("\x1b[?25h")
            sys.stdout.flush()

        print(json.dumps({"run_id": state.run_id, "status": state.status, "current_stage": state.current_stage}))
        return 0

    if args.command == "inspect":
        roles = load_roles(args.roles_dir)
        for role_name in sorted(roles):
            print(role_name)
        return 0

    base_dir = Path(args.roles_dir).resolve().parents[0] if args.roles_dir else Path(__file__).resolve().parents[2]
    app = build_default_app(base_dir)
    if args.runs_dir:
        app.runs_dir = Path(args.runs_dir)
    extra_params = {}
    for p in args.params or []:
        if "=" in p:
            k, v = p.split("=", 1)
            extra_params[k.strip()] = v.strip()

    state = app.run(
        RunConfig(
            task_id=args.task_id,
            task=args.task,
            runner=args.runner,
            target_branch=args.target_branch,
            namespace=args.namespace,
            service=args.service,
            tags=args.tags,
            extra_params=extra_params or None,
            first_role=args.first_role,
            last_role=args.last_role,
        )
    )
    print(json.dumps({"run_id": state.run_id, "status": state.status, "current_stage": state.current_stage}))
    return 0
