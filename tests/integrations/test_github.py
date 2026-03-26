from __future__ import annotations

import pytest

from devpipe.integrations.github import GitHubAdapter, GitHubWorkflowError


def test_github_adapter_extracts_failure_summary() -> None:
    adapter = GitHubAdapter(client=lambda run_id: {"conclusion": "failure", "jobs": [{"name": "test", "status": "failed"}]})

    with pytest.raises(GitHubWorkflowError) as exc:
        adapter.ensure_workflow_success("123")

    assert "test" in str(exc.value)
