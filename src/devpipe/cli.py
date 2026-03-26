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

# Single combined regex strips all ESC sequences in one pass
_ANSI_RE = re.compile(
    r"\x1b\[[\x20-\x3f]*[\x40-\x7e]"           # CSI  (colors, cursor, modes…)
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"       # OSC
    r"|\x1b[\x20-\x2f]*[\x30-\x7e]"             # other 2-char ESC sequences
)
# Residual coordinate fragments when ESC+[ arrived in the previous chunk, e.g. "32;16H"
_COORD_RE = re.compile(r"\[?[\d;?=><!]+[A-Za-z@]")
# Incomplete ESC at end of chunk (will be prepended to next chunk)
_PARTIAL_ESC = re.compile(r"\x1b(?:\[[\x20-\x3f]*)?$")


def _clean(s: str) -> str:
    s = _ANSI_RE.sub("", s)
    # Remove residuals that look like terminal parameter sequences
    # Only strip if they start right after a stripped spot or line boundary
    s = re.sub(r"(?:^|(?<=\n))\s*[\d;?=><!]+[A-Za-z@]", "", s)
    # Remove remaining control chars (keep \n and \t)
    s = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", s)
    return s.replace("\r", "")


_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# Panel occupies: blank + top-border + content + bottom-border + blank = 5 lines
# Spinner line = 1 line → reserve 6 lines, rest goes to output
_PANEL_OVERHEAD = 6


class _RunProgress:
    def __init__(self, stages: list[str], console: Console) -> None:
        self.stages = stages
        self.current_stage = ""
        self._console = console
        self._buf: list[str] = []
        self._tick = 0
        self._area_drawn = False  # whether the live area has been printed
        self._drawn_n = 0         # number of output lines in the current area
        self._esc_carry = ""     # incomplete ESC sequence from previous chunk

    @staticmethod
    def _n() -> int:
        return max(1, shutil.get_terminal_size().lines - _PANEL_OVERHEAD)

    # ── public API ────────────────────────────────────────────────────────────

    def set_stage(self, stage: str) -> None:
        self.current_stage = stage
        self._buf = []
        self._tick = 0
        self._area_drawn = False
        self._esc_carry = ""

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
        # flush Rich's buffer before raw writes
        self._console.file.flush()
        self._draw()

    def on_output(self, text: str) -> None:
        # Prepend any incomplete ESC sequence carried over from the previous chunk
        text = self._esc_carry + text
        # Save a trailing incomplete ESC sequence for the next chunk
        m = _PARTIAL_ESC.search(text)
        if m:
            self._esc_carry = m.group()
            text = text[: m.start()]
        else:
            self._esc_carry = ""

        for line in _clean(text).split("\n"):
            line = line.strip()
            if line:
                self._buf.append(line)
        self._tick += 1
        self._draw()

    # ── internal ──────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        n = self._n()
        ts = shutil.get_terminal_size()
        w = max(ts.columns - 6, 20)

        if self._area_drawn:
            # Move back to the spinner line of the current area
            sys.stdout.write(f"\x1b[{self._drawn_n + 1}A")

        spinner = _SPINNER[self._tick % len(_SPINNER)]
        sys.stdout.write(f"\x1b[2K\r  {spinner}  {self.current_stage}\n")

        visible = ([""] * n + self._buf)[-n:]
        for line in visible:
            if len(line) > w:
                line = line[: w - 1] + "…"
            sys.stdout.write(f"\x1b[2K\r  \x1b[2m{line}\x1b[0m\n")

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
            console.print("\n[dim]interrupted[/dim]")
            return 130
        finally:
            sys.stdout.write("\x1b[?25h")  # restore cursor
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
