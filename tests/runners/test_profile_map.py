from __future__ import annotations

import pytest

from devpipe.runners.profile_map import (
    load_runner_profiles,
    resolve_effort,
    resolve_model,
)


def _profiles():
    return load_runner_profiles(
        {
            "runners": {
                "codex": {
                    "model": {
                        "low": "gpt-5.4-mini",
                        "middle": "gpt-5.3-codex",
                        "high": "gpt-5.4",
                    },
                    "effort": {
                        "low": "low",
                        "middle": "medium",
                        "high": "hight",
                        "extra": "extra-hight",
                    },
                },
                "claude": {
                    "model": {
                        "low": "Haiku 4.5",
                        "middle": "Sonnet 4.6",
                        "high": "Opus 4.6",
                    },
                    "effort": {
                        "low": "low",
                        "middle": "medium",
                        "high": "hight",
                        "extra": "hight",
                    },
                },
            }
        }
    )


def test_resolve_model_maps_levels_per_runner() -> None:
    profiles = _profiles()
    assert resolve_model(profiles, "codex", "low") == "gpt-5.4-mini"
    assert resolve_model(profiles, "codex", "middle") == "gpt-5.3-codex"
    assert resolve_model(profiles, "codex", "high") == "gpt-5.4"
    assert resolve_model(profiles, "claude", "low") == "Haiku 4.5"
    assert resolve_model(profiles, "claude", "middle") == "Sonnet 4.6"
    assert resolve_model(profiles, "claude", "high") == "Opus 4.6"


def test_resolve_effort_maps_levels_per_runner() -> None:
    profiles = _profiles()
    assert resolve_effort(profiles, "codex", "low") == "low"
    assert resolve_effort(profiles, "codex", "middle") == "medium"
    assert resolve_effort(profiles, "codex", "high") == "hight"
    assert resolve_effort(profiles, "codex", "extra") == "extra-hight"
    assert resolve_effort(profiles, "claude", "low") == "low"
    assert resolve_effort(profiles, "claude", "middle") == "medium"
    assert resolve_effort(profiles, "claude", "high") == "hight"
    assert resolve_effort(profiles, "claude", "extra") == "hight"


def test_resolve_model_rejects_unknown_level() -> None:
    profiles = _profiles()
    with pytest.raises(ValueError):
        resolve_model(profiles, "codex", "ultra")


def test_resolve_effort_rejects_unknown_runner() -> None:
    profiles = _profiles()
    with pytest.raises(ValueError):
        resolve_effort(profiles, "unknown", "low")
