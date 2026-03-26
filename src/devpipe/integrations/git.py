from __future__ import annotations

import re
import subprocess


class GitAdapter:
    def __init__(self, exec_fn=subprocess.run) -> None:
        self.exec_fn = exec_fn

    def current_branch(self) -> str:
        result = self.exec_fn(["git", "branch", "--show-current"], text=True, capture_output=True)
        return result.stdout.strip()

    def extract_task_id(self, branch_name: str) -> str | None:
        match = re.search(r"(MRC-\d+)", branch_name)
        return match.group(1) if match else None

    def commit(self, message: str) -> None:
        self.exec_fn(["git", "commit", "-am", message], text=True, capture_output=True)

    def push(self) -> None:
        self.exec_fn(["git", "push"], text=True, capture_output=True)

