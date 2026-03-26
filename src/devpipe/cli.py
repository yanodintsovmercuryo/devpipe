from __future__ import annotations

import argparse
import json
import os
import re
import select as _select
import shutil
import sys
import termios
import tty
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
        self._buf: list[str] = []   # all output lines across all stages
        self._carry = ""            # incomplete ESC from previous chunk
        self._current_line = ""     # partial line (no \n yet)
        self._tick = 0
        self._drawn_n = 0
        self._scroll = 0            # lines from bottom; 0 = follow tail
        self._kbd_buf = b""         # partial keyboard escape sequence

    # ── stage header ─────────────────────────────────────────────────────────

    def set_stage(self, stage: str) -> None:
        self.current_stage = stage
        if stage == self._printed_stage:
            return
        self._printed_stage = stage
        # flush current partial line and add a stage separator
        if self._current_line.strip():
            self._buf.append(self._current_line)
        if self._buf:  # blank separator before new stage (not at very start)
            self._buf.append("")
        self._buf.append(f"\x1b[2m── {stage} ──\x1b[0m")
        self._carry = ""
        self._current_line = ""
        self._tick = 0
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

    # ── keyboard input (scroll) ───────────────────────────────────────────────

    def _adjust_scroll(self, delta: int, n_visible: int) -> None:
        total = len(self._buf)
        max_scroll = max(0, total - n_visible)
        self._scroll = max(0, min(self._scroll + delta, max_scroll))

    def _process_input(self, n_visible: int) -> None:
        """Read pending keystrokes/mouse events non-blocking and update _scroll."""
        try:
            fd = sys.stdin.fileno()
            while _select.select([fd], [], [], 0)[0]:
                ch = os.read(fd, 1)
                self._kbd_buf += ch

                # bare ESC — wait briefly for more bytes
                if self._kbd_buf == b"\x1b":
                    if _select.select([fd], [], [], 0.02)[0]:
                        continue
                    else:
                        self._kbd_buf = b""
                        break

                if self._kbd_buf.startswith(b"\x1b["):
                    # SGR mouse: \x1b[<...M or \x1b[<...m  (variable length, ends with M/m)
                    if len(self._kbd_buf) >= 3 and self._kbd_buf[2:3] == b"<":
                        last = self._kbd_buf[-1:]
                        if last not in (b"M", b"m"):
                            if _select.select([fd], [], [], 0.02)[0]:
                                continue
                            self._kbd_buf = b""
                            break
                        seq = self._kbd_buf
                        self._kbd_buf = b""
                        try:
                            inner = seq[3:-1].decode()   # e.g. "64;10;5"
                            btn = int(inner.split(";")[0])
                            if btn == 64:                # wheel up
                                self._adjust_scroll(3, n_visible)
                            elif btn == 65:              # wheel down
                                self._adjust_scroll(-3, n_visible)
                        except (ValueError, IndexError):
                            pass
                        break

                    # wait for short sequences that aren't complete yet
                    if len(self._kbd_buf) < 4:
                        if _select.select([fd], [], [], 0.02)[0]:
                            continue

                seq = self._kbd_buf
                self._kbd_buf = b""
                total = len(self._buf)
                max_scroll = max(0, total - n_visible)
                if seq in (b"\x1b[A", b"k"):        # up arrow / k
                    self._adjust_scroll(1, n_visible)
                elif seq in (b"\x1b[B", b"j"):      # down arrow / j
                    self._adjust_scroll(-1, n_visible)
                elif seq == b"\x1b[5~":             # page up
                    self._adjust_scroll(n_visible, n_visible)
                elif seq == b"\x1b[6~":             # page down
                    self._adjust_scroll(-n_visible, n_visible)
                elif seq in (b"g", b"\x1b[H"):      # Home / g
                    self._scroll = max_scroll
                elif seq in (b"G", b"\x1b[F"):      # End / G
                    self._scroll = 0
                break
        except (OSError, IOError):
            pass

    # ── in-place panel + window ───────────────────────────────────────────────

    def _draw_panel(self, spinner: str, scrolled: bool) -> None:
        W = shutil.get_terminal_size().columns
        idx = self.stages.index(self.current_stage) if self.current_stage in self.stages else -1
        parts: list[str] = []
        for i, s in enumerate(self.stages):
            if i < idx:
                parts.append(f"\x1b[2;32m{s}\x1b[0m")
            elif s == self.current_stage:
                parts.append(f"\x1b[1;36m{spinner} {s}\x1b[0m")
            else:
                parts.append(f"\x1b[2m{s}\x1b[0m")
        content = "  ".join(parts)
        plain_content = re.sub(r"\x1b\[[0-9;:]*m", "", content)

        scroll_tag = ""
        scroll_tag_plain = ""
        if scrolled:
            scroll_tag = f"  \x1b[2m↑ scroll\x1b[0m"
            scroll_tag_plain = "  ↑ scroll"

        title = " devpipe "
        inner = W - 2
        left_d = max(0, (inner - len(title)) // 2)
        right_d = max(0, inner - len(title) - left_d)
        used = len(plain_content) + len(scroll_tag_plain)
        pad = max(0, inner - 2 - used)

        B = "\x1b[34m"; R = "\x1b[0m"; T = "\x1b[1;34m"
        sys.stdout.write(f"\x1b[2K\r\n")
        sys.stdout.write(f"\x1b[2K\r{B}╭{'─'*left_d}{T}{title}{B}{'─'*right_d}╮{R}\n")
        sys.stdout.write(f"\x1b[2K\r{B}│{R} {content}{scroll_tag}{' '*pad} {B}│{R}\n")
        sys.stdout.write(f"\x1b[2K\r{B}╰{'─'*inner}╯{R}\n")
        sys.stdout.write(f"\x1b[2K\r\n")

    def _draw(self) -> None:
        n = max(1, shutil.get_terminal_size().lines - _PANEL_LINES - 1)
        w = max(shutil.get_terminal_size().columns - 4, 20)

        self._process_input(n)

        spinner = _SPINNER[self._tick % len(_SPINNER)]

        display = self._buf + ([self._current_line] if self._current_line.strip() else [])
        total = len(display)
        # clamp scroll so it can't exceed available lines
        max_scroll = max(0, total - n)
        self._scroll = min(self._scroll, max_scroll)

        if self._scroll > 0:
            end = total - self._scroll
            visible = display[max(0, end - n):end]
        else:
            visible = display[-n:]

        sys.stdout.write("\x1b[H")  # cursor to top-left
        self._draw_panel(spinner, scrolled=self._scroll > 0)

        for line in visible:
            plain = re.sub(r"\x1b\[[0-9;]*m", "", line)
            if len(plain) > w:
                line = plain[: w - 1] + "…"
            sys.stdout.write(f"\x1b[2K\r{line}\n")

        sys.stdout.write("\x1b[J")
        sys.stdout.write("\x1b[0m")
        sys.stdout.flush()
        self._drawn_n = len(visible)

    def finish(self, status: str, run_id: str) -> None:
        """Exit alternate screen and show a single status line in the main terminal."""
        sys.stdout.write("\x1b[?1006l\x1b[?1000l")  # disable mouse reporting
        sys.stdout.write("\x1b[?1049l")  # exit alternate screen → back to main terminal

        if status == "completed":
            line = f"\x1b[1;32m✓  completed\x1b[0m  \x1b[2m{run_id}\x1b[0m"
        else:
            line = f"\x1b[1;31m✗  failed\x1b[0m  \x1b[2m{run_id}\x1b[0m"

        sys.stdout.write(f"{line}\n")
        sys.stdout.write("\x1b[0m")
        sys.stdout.flush()


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

        _stdin_fd = sys.stdin.fileno() if sys.stdin.isatty() else None
        _old_term = termios.tcgetattr(_stdin_fd) if _stdin_fd is not None else None

        sys.stdout.write("\x1b[?1049h")  # enter alternate screen
        sys.stdout.flush()

        try:
            config = run_tui(base_dir)
        except KeyboardInterrupt:
            config = None
        except Exception:
            sys.stdout.write("\x1b[?1049l")
            sys.stdout.flush()
            raise

        if config is None:
            sys.stdout.write("\x1b[?1049l")  # exit alternate screen — back to normal terminal
            sys.stdout.flush()
            return 0

        app = build_default_app(base_dir)

        first = config.first_role or STAGE_ORDER[0]
        last = config.last_role or STAGE_ORDER[-1]
        fi = STAGE_ORDER.index(first) if first in STAGE_ORDER else 0
        li = STAGE_ORDER.index(last) if last in STAGE_ORDER else len(STAGE_ORDER) - 1
        active_stages = STAGE_ORDER[fi: li + 1]

        console = Console()
        sys.stdout.write("\x1b[?25l")  # hide cursor
        sys.stdout.flush()

        # Disable echo + enable mouse wheel reporting
        if _stdin_fd is not None:
            tty.setcbreak(_stdin_fd)  # cbreak: no echo, but Ctrl+C still sends SIGINT
        sys.stdout.write("\x1b[?1000h\x1b[?1006h")  # enable mouse reporting (SGR mode)
        sys.stdout.flush()

        progress = _RunProgress(active_stages, console)
        runner = app.runners[config.runner]
        runner.output_callback = progress.on_output  # type: ignore[union-attr]

        try:
            state = app.run(config, on_stage_start=progress.set_stage)
        except KeyboardInterrupt:
            if _stdin_fd is not None and _old_term is not None:
                termios.tcsetattr(_stdin_fd, termios.TCSADRAIN, _old_term)
            sys.stdout.write("\x1b[?1006l\x1b[?1000l")  # disable mouse
            sys.stdout.write("\x1b[?1049l")  # exit alternate screen
            sys.stdout.write("\x1b[?25h\n")
            sys.stdout.flush()
            console.print("[dim]interrupted[/dim]")
            return 130
        except Exception:
            if _stdin_fd is not None and _old_term is not None:
                termios.tcsetattr(_stdin_fd, termios.TCSADRAIN, _old_term)
            sys.stdout.write("\x1b[?1006l\x1b[?1000l")  # disable mouse
            sys.stdout.write("\x1b[?1049l")
            sys.stdout.write("\x1b[?25h\n")
            sys.stdout.flush()
            raise
        finally:
            if _stdin_fd is not None and _old_term is not None:
                termios.tcsetattr(_stdin_fd, termios.TCSADRAIN, _old_term)
            sys.stdout.write("\x1b[?1006l\x1b[?1000l")  # disable mouse
            sys.stdout.write("\x1b[?25h")
            sys.stdout.flush()

        progress.finish(state.status, state.run_id)
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
