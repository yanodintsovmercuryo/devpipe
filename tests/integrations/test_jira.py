from __future__ import annotations

from devpipe.integrations.jira import JiraAdapter


def test_jira_adapter_degrades_cleanly() -> None:
    adapter = JiraAdapter(client=None)

    issue = adapter.fetch_issue("MRC-1")

    assert issue["available"] is False
    assert issue["task_id"] == "MRC-1"
