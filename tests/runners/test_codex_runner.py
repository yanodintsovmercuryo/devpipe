from __future__ import annotations

import subprocess

import pytest

from devpipe.roles.envelope import TaskEnvelope
from devpipe.runners.codex import CodexRunner
from devpipe.runners.base import InvalidRunnerOutputError, RunnerTimeoutError


def _envelope() -> TaskEnvelope:
    return TaskEnvelope(
        role="architect",
        goal="Create a plan",
        instructions="Return JSON",
        context={"task": "Implement feature"},
        artifacts={},
        constraints=[],
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
    )


def test_codex_runner_returns_structured_output() -> None:
    def fake_exec(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout='```json\n{"summary":"done"}\n```',
            stderr="",
        )

    runner = CodexRunner(exec_fn=fake_exec)
    result = runner.run(_envelope())

    assert result.ok is True
    assert result.structured_output["summary"] == "done"


def test_codex_runner_raises_timeout() -> None:
    def fake_exec(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["codex"], timeout=10)

    runner = CodexRunner(exec_fn=fake_exec)

    with pytest.raises(RunnerTimeoutError):
        runner.run(_envelope())


def test_codex_runner_rejects_invalid_output() -> None:
    def fake_exec(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["codex"], returncode=0, stdout='{"bad":true}', stderr="")

    runner = CodexRunner(exec_fn=fake_exec)

    with pytest.raises(InvalidRunnerOutputError):
        runner.run(_envelope())
