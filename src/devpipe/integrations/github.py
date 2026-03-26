from __future__ import annotations


class GitHubWorkflowError(RuntimeError):
    pass


class GitHubAdapter:
    def __init__(self, client) -> None:
        self.client = client

    def ensure_workflow_success(self, run_id: str) -> dict[str, object]:
        payload = self.client(run_id)
        if payload.get("conclusion") == "success":
            return payload
        failed_jobs = [job.get("name", "unknown") for job in payload.get("jobs", []) if job.get("status") == "failed"]
        raise GitHubWorkflowError(f"Workflow {run_id} failed: {', '.join(failed_jobs) or 'unknown failure'}")

