from __future__ import annotations

from devpipe.roles.envelope import TaskEnvelope
from devpipe.runners.base import BaseCliRunner


class CodexRunner(BaseCliRunner):
    """Runner for the OpenAI Codex CLI.

    Codex is an interactive TUI tool (prompt_toolkit).  Writing a multiline
    prompt to its stdin via PTY doesn't work: each newline is treated as an
    Enter key-press that submits only that line.  Instead we pass the full
    prompt as a positional CLI argument and use --full-auto so codex runs
    without asking for approval.  PTY is still used for stdin so codex's
    "stdin is not a terminal" check passes; we send EOF (Ctrl-D) immediately
    since the task is already in the argument.
    """

    def __init__(self, command: list[str] | None = None, **kwargs) -> None:
        kwargs.setdefault("use_pty", True)
        kwargs.setdefault("forward_to_tty", False)
        super().__init__(command=command or ["codex"], **kwargs)

    def _get_command_and_input(self, envelope: TaskEnvelope) -> tuple[list[str], str]:
        prompt = self.build_prompt(envelope)
        command = self.command + [
            "--dangerously-bypass-approvals-and-sandbox",
            prompt,
        ]
        return command, ""  # empty stdin → EOF sent immediately via PTY
