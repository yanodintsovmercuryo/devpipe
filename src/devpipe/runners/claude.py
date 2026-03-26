from __future__ import annotations

from devpipe.runners.base import BaseCliRunner


class ClaudeRunner(BaseCliRunner):
    def __init__(self, command: list[str] | None = None, **kwargs) -> None:
        super().__init__(command=command or ["claude"], **kwargs)
