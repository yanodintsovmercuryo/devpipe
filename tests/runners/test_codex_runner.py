from __future__ import annotations

import json
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
        model_name="gpt-5.4",
        effort="high",
        context={"task": "Implement feature"},
        artifacts={},
        constraints=[],
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
    )


def test_codex_runner_returns_structured_output() -> None:
    runner = CodexRunner()

    def fake_run_pty(envelope: TaskEnvelope):
        command, _ = runner._get_command_and_input(envelope)
        assert "-m" in command
        assert "gpt-5.4" in command
        assert '-c' in command
        assert 'model_reasoning_effort="high"' in command
        assert runner._output_file is not None
        with open(runner._output_file, "w", encoding="utf-8") as f:
            json.dump({"summary": "done"}, f)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    runner._run_pty = fake_run_pty  # type: ignore[method-assign]
    result = runner.run(_envelope())

    assert result.ok is True
    assert result.structured_output["summary"] == "done"


def test_codex_runner_raises_timeout() -> None:
    runner = CodexRunner()
    runner._run_pty = lambda _envelope: (_ for _ in ()).throw(RunnerTimeoutError("timed out"))  # type: ignore[method-assign]

    with pytest.raises(RunnerTimeoutError):
        runner.run(_envelope())


def test_codex_runner_rejects_invalid_output() -> None:
    runner = CodexRunner()

    def fake_run_pty(envelope: TaskEnvelope):
        command, _ = runner._get_command_and_input(envelope)
        assert runner._output_file is not None
        with open(runner._output_file, "w", encoding="utf-8") as f:
            f.write('{"bad":true}')
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    runner._run_pty = fake_run_pty  # type: ignore[method-assign]

    with pytest.raises(InvalidRunnerOutputError):
        runner.run(_envelope())
