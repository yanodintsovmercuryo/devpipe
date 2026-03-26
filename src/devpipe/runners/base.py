from __future__ import annotations

import os
import pty
import select
import subprocess
import termios
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from devpipe.roles.envelope import TaskEnvelope, TaskResult
from devpipe.roles.parser import OutputParseError, OutputParser


class RunnerError(RuntimeError):
    pass


class RunnerTimeoutError(RunnerError):
    pass


class InvalidRunnerOutputError(RunnerError):
    pass


class CommandFailedError(RunnerError):
    pass


ExecFn = Callable[..., subprocess.CompletedProcess]


class Runner(Protocol):
    def run(self, envelope: TaskEnvelope) -> TaskResult:
        ...


def _run_with_pty(
    command: list[str],
    input: str,
    timeout: int,
    env: dict[str, str] | None,
    output_callback: "Callable[[str], None] | None" = None,
) -> subprocess.CompletedProcess:
    """Run command with PTY for stdin+stdout so all TTY checks pass.

    Uses the same PTY slave for stdin and stdout; stderr is captured via pipe.
    Input is written to master_fd; output is drained from master_fd until the
    process exits.  Two Ctrl-D (EOT) characters are appended to signal EOF
    after the prompt (works in canonical TTY mode regardless of trailing newline).
    """
    master_fd, slave_fd = pty.openpty()
    # Disable echo so the prompt bytes don't appear in the captured output.
    try:
        attrs = termios.tcgetattr(slave_fd)
        attrs[3] &= ~termios.ECHO  # lflags
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)
    except termios.error:
        pass

    proc = subprocess.Popen(
        command,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=subprocess.PIPE,
        close_fds=True,
        env=env,
    )
    os.close(slave_fd)

    # Write input + EOF using bidirectional select to prevent TTY buffer
    # deadlock: large prompts exceed the ~4 KB PTY kernel buffer, so we must
    # drain output while writing input.
    to_write = input.encode() + b"\x04\x04"
    write_offset = 0
    write_done = False
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            proc.kill()
            proc.communicate()
            try:
                os.close(master_fd)
            except OSError:
                pass
            raise subprocess.TimeoutExpired(command, timeout)

        wlist = [] if write_done else [master_fd]
        r, w, _ = select.select([master_fd], wlist, [], min(remaining, 0.5))

        # Write a chunk of input when the master fd is writable
        if w and not write_done:
            chunk = to_write[write_offset: write_offset + 4096]
            try:
                n = os.write(master_fd, chunk)
                write_offset += n
            except OSError:
                write_done = True
            if write_offset >= len(to_write):
                write_done = True

        # Read output
        if r:
            try:
                data = os.read(master_fd, 4096)
                if data:
                    chunks.append(data)
                    if output_callback:
                        output_callback(data.decode(errors="replace"))
            except OSError:
                break

        if proc.poll() is not None:
            # Drain any remaining bytes.
            while True:
                try:
                    r2, _, _ = select.select([master_fd], [], [], 0.1)
                    if not r2:
                        break
                    data = os.read(master_fd, 4096)
                    if data:
                        chunks.append(data)
                        if output_callback:
                            output_callback(data.decode(errors="replace"))
                    else:
                        break
                except OSError:
                    break
            break

    _, stderr_bytes = proc.communicate(timeout=5)
    try:
        os.close(master_fd)
    except OSError:
        pass

    stdout = b"".join(chunks).decode(errors="replace")
    stderr = (stderr_bytes or b"").decode(errors="replace")
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


@dataclass
class BaseCliRunner:
    command: list[str]
    timeout: int = 300
    env: dict[str, str] = field(default_factory=dict)
    exec_fn: ExecFn = subprocess.run
    use_pty: bool = False
    output_callback: "Callable[[str], None] | None" = None

    def build_prompt(self, envelope: TaskEnvelope) -> str:
        return (
            f"Role: {envelope.role}\n"
            f"Goal: {envelope.goal}\n"
            f"Instructions:\n{envelope.instructions}\n\n"
            f"Context: {envelope.context}\n"
            f"Constraints: {envelope.constraints}\n"
            f"Output schema: {envelope.output_schema}\n"
        )

    def _get_command_and_input(self, envelope: TaskEnvelope) -> tuple[list[str], str]:
        """Return (command, stdin_text) to use for this envelope.

        Subclasses can override to pass the prompt as a CLI argument instead
        of via stdin (e.g. for interactive TUI runners like codex).
        """
        return self.command, self.build_prompt(envelope)

    def run(self, envelope: TaskEnvelope) -> TaskResult:
        command, prompt = self._get_command_and_input(envelope)
        try:
            if self.use_pty:
                completed = _run_with_pty(
                    command,
                    input=prompt,
                    timeout=self.timeout,
                    env=self.env or None,
                    output_callback=self.output_callback,
                )
            else:
                completed = self.exec_fn(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout,
                    env=self.env or None,
                )
        except subprocess.TimeoutExpired as exc:
            raise RunnerTimeoutError(str(exc)) from exc

        if completed.returncode != 0:
            raise CommandFailedError(completed.stderr or f"Runner exited with code {completed.returncode}")

        parser = OutputParser(envelope.output_schema)
        try:
            structured_output = parser.parse(completed.stdout)
        except OutputParseError as exc:
            raise InvalidRunnerOutputError(str(exc)) from exc

        return TaskResult(
            ok=True,
            summary=str(structured_output.get("summary", "")),
            structured_output=structured_output,
            artifacts={},
            next_hints=[],
            error_type=None,
            error_message=None,
            transcript=completed.stdout,
        )
