from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetryPolicy:
    default_limit: int = 1
    stage_limits: dict[str, int] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "RetryPolicy":
        return cls(
            default_limit=1,
            stage_limits={
                "architect": 2,
                "developer": 2,
                "test_developer": 2,
                "qa_local": 2,
                "release": 1,
                "qa_stand": 1,
            },
        )

    def limit_for(self, stage: str) -> int:
        return self.stage_limits.get(stage, self.default_limit)

    def should_retry(self, stage: str, attempts_so_far: int) -> bool:
        return attempts_so_far < self.limit_for(stage)
