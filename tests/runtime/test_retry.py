from __future__ import annotations

from devpipe.runtime.retry import RetryPolicy


def test_retry_policy_uses_stage_specific_limit() -> None:
    policy = RetryPolicy(default_limit=1, stage_limits={"qa_local": 3})

    assert policy.should_retry("qa_local", 0) is True
    assert policy.should_retry("qa_local", 2) is True
    assert policy.should_retry("qa_local", 3) is False


def test_retry_policy_falls_back_to_default_limit() -> None:
    policy = RetryPolicy(default_limit=2)

    assert policy.should_retry("developer", 1) is True
    assert policy.should_retry("developer", 2) is False
