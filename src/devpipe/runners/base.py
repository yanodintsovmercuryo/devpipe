from __future__ import annotations

import subprocess
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


@dataclass
class BaseCliRunner:
    command: list[str]
    timeout: int = 300
    env: dict[str, str] = field(default_factory=dict)
    exec_fn: ExecFn = subprocess.run

    def build_prompt(self, envelope: TaskEnvelope) -> str:
        return (
            f"Role: {envelope.role}\n"
            f"Goal: {envelope.goal}\n"
            f"Instructions:\n{envelope.instructions}\n\n"
            f"Context: {envelope.context}\n"
            f"Constraints: {envelope.constraints}\n"
            f"Output schema: {envelope.output_schema}\n"
        )

    def run(self, envelope: TaskEnvelope) -> TaskResult:
        prompt = self.build_prompt(envelope)
        try:
            completed = self.exec_fn(
                self.command,
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
