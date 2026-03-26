from __future__ import annotations

from typing import Any

MODEL_LEVELS = ("low", "middle", "high")
EFFORT_LEVELS = ("low", "middle", "high", "extra")

RunnerProfiles = dict[str, dict[str, dict[str, str]]]


def validate_runner_profiles(profiles: RunnerProfiles) -> RunnerProfiles:
    for runner in profiles:
        model_map = profiles[runner].get("model", {})
        effort_map = profiles[runner].get("effort", {})
        for level in MODEL_LEVELS:
            if level not in model_map:
                raise ValueError(f"Runner '{runner}' is missing model mapping for level '{level}'")
        for level in EFFORT_LEVELS:
            if level not in effort_map:
                raise ValueError(f"Runner '{runner}' is missing effort mapping for level '{level}'")
    return profiles


def load_runner_profiles(raw: dict[str, Any]) -> RunnerProfiles:
    runners = raw.get("runners")
    if not isinstance(runners, dict):
        raise ValueError("runner profiles config must contain top-level 'runners' map")
    return validate_runner_profiles(runners)  # type: ignore[arg-type]


def resolve_model(profiles: RunnerProfiles, runner: str, level: str) -> str:
    try:
        return profiles[runner]["model"][level]
    except KeyError as exc:
        raise ValueError(f"Unsupported model level '{level}' for runner '{runner}'") from exc


def resolve_effort(profiles: RunnerProfiles, runner: str, level: str) -> str:
    try:
        return profiles[runner]["effort"][level]
    except KeyError as exc:
        raise ValueError(f"Unsupported effort level '{level}' for runner '{runner}'") from exc
