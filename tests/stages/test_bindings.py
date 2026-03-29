"""Tests for declarative binding resolution."""
from __future__ import annotations

import pytest

from devpipe.bindings import resolve_bindings, BindingError


def test_resolve_input_binding():
    """Resolve input.<key> from inputs dict."""
    context = {
        "inputs": {"task": "Implement feature X", "env": "prod"},
        "stages": {},
        "context": {},
        "runtime": {},
        "integration": {},
    }
    bindings = {"task_input": "input.task", "env_input": "input.env"}
    resolved = resolve_bindings(bindings, context)
    assert resolved["task_input"] == "Implement feature X"
    assert resolved["env_input"] == "prod"


def test_resolve_stage_output_binding():
    """Resolve stage.<stage>.out.<field> from stage outputs."""
    context = {
        "inputs": {},
        "stages": {
            "developer": {"code_files": ["main.py"], "tests": ["test_main.py"]},
            "qa": {"approved": True},
        },
        "context": {},
        "runtime": {},
        "integration": {},
    }
    bindings = {
        "dev_code": "stage.developer.out.code_files",
        "qa_ok": "stage.qa.out.approved",
    }
    resolved = resolve_bindings(bindings, context)
    assert resolved["dev_code"] == ["main.py"]
    assert resolved["qa_ok"] is True


def test_resolve_out_shortcut_with_current_stage():
    """Resolve out.<field> using _current_stage in context."""
    context = {
        "inputs": {},
        "stages": {"builder": {"artifact": "build.tar.gz"}},
        "context": {},
        "runtime": {},
        "integration": {},
        "_current_stage": "builder",
    }
    bindings = {"artifact": "out.artifact"}
    resolved = resolve_bindings(bindings, context)
    assert resolved["artifact"] == "build.tar.gz"


def test_resolve_out_shortcut_fails_without_current_stage():
    """out.<field> requires _current_stage in context."""
    context = {
        "inputs": {},
        "stages": {"builder": {"artifact": "build.tar.gz"}},
        "context": {},
        "runtime": {},
        "integration": {},
    }
    bindings = {"artifact": "out.artifact"}
    with pytest.raises(BindingError, match="_current_stage"):
        resolve_bindings(bindings, context)


def test_resolve_context_binding():
    """Resolve context.<key> from shared_context."""
    context = {
        "inputs": {},
        "stages": {},
        "context": {"shared": {"token": "abc123"}, "user": "alice"},
        "runtime": {},
        "integration": {},
    }
    bindings = {"token": "context.shared.token", "user": "context.user"}
    resolved = resolve_bindings(bindings, context)
    assert resolved["token"] == "abc123"
    assert resolved["user"] == "alice"


def test_resolve_runtime_binding():
    """Resolve runtime.<key> from runtime dict."""
    context = {
        "inputs": {},
        "stages": {},
        "context": {},
        "runtime": {"git": {"current_branch": "feature-xyz"}, "timestamp": "2025-01-01T00:00:00Z"}
    }
    bindings = {"branch": "runtime.git.current_branch", "ts": "runtime.timestamp"}
    resolved = resolve_bindings(bindings, context)
    assert resolved["branch"] == "feature-xyz"
    assert resolved["ts"] == "2025-01-01T00:00:00Z"


def test_resolve_integration_binding():
    """Resolve integration.<key> from integration dict."""
    context = {
        "inputs": {},
        "stages": {},
        "context": {},
        "runtime": {},
        "integration": {"jira": {"issue": {"key": "ABC-123", "summary": "Test"}}},
    }
    bindings = {"jira_key": "integration.jira.issue.key", "jira_summary": "integration.jira.issue.summary"}
    resolved = resolve_bindings(bindings, context)
    assert resolved["jira_key"] == "ABC-123"
    assert resolved["jira_summary"] == "Test"


def test_resolve_invalid_prefix():
    """Unsupported prefix raises error."""
    context = {
        "inputs": {},
        "stages": {},
        "context": {},
        "runtime": {},
        "integration": {},
    }
    bindings = {"x": "invalid.prefix"}
    with pytest.raises(BindingError, match="unsupported source path"):
        resolve_bindings(bindings, context)


def test_resolve_missing_key_returns_none():
    """Missing key returns None (dict.get)."""
    context = {
        "inputs": {"exists": "yes"},
        "stages": {},
        "context": {},
        "runtime": {},
        "integration": {},
    }
    bindings = {"missing": "input.not_exists"}
    resolved = resolve_bindings(bindings, context)
    assert resolved["missing"] is None
