from __future__ import annotations


class JiraAdapter:
    def __init__(self, client=None) -> None:
        self.client = client

    def fetch_issue(self, task_id: str) -> dict[str, object]:
        if self.client is None:
            return {
                "available": False,
                "task_id": task_id,
                "title": None,
                "description": None,
                "comments": [],
                "linked_issues": [],
            }
        issue = self.client(task_id)
        issue["available"] = True
        return issue

