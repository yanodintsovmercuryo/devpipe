from __future__ import annotations

from devpipe.runtime.retry import RetryPolicy
from devpipe.runtime.state import STAGE_ORDER


def first_stage() -> str:
    return STAGE_ORDER[0]


def next_stage(current_stage: str) -> str:
    if current_stage not in STAGE_ORDER:
        return first_stage()
    current_index = STAGE_ORDER.index(current_stage)
    if current_index + 1 >= len(STAGE_ORDER):
        return "completed"
    return STAGE_ORDER[current_index + 1]


def should_retry_stage(stage: str, attempts_so_far: int, retry_policy: RetryPolicy) -> bool:
    return retry_policy.should_retry(stage, attempts_so_far)
