from __future__ import annotations

from types import SimpleNamespace

from devpipe import history
from devpipe.runtime.state import PipelineState


def test_save_run_creates_initial_entry(tmp_path, monkeypatch) -> None:
    """Initial save_run creates entry with running status."""
    history_dir = tmp_path / "history"
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "_now_iso", lambda: "2026-03-28 10:00:00")

    config = SimpleNamespace(
        task="Build feature X",
        task_id="MRC-1",
        runner="codex",
        model="auto",
        effort="auto",
        target_branch="main",
        service="acquiring",
        namespace="u1",
        tags=["go"],
        extra_params={},
        first_role="architect",
        last_role="qa_stand",
        profile="test-profile",
    )

    state = PipelineState.create(
        task_id="MRC-1",
        task_text="Build feature X",
        selected_runner="codex",
        run_id="test-run-123",
    )
    state.status = "running"

    history.save_run(config, state)

    entries = history.load_history(profile="test-profile")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["run_id"] == "test-run-123"
    assert entry["profile"] == "test-profile"
    assert entry["status"] == "running"
    assert entry["date"] == "2026-03-28 10:00:00"
    assert "finished_at" not in entry
    assert "attempts" not in entry


def test_save_run_updates_existing_entry_with_final_status(tmp_path, monkeypatch) -> None:
    """Second save_run with final status updates existing entry and sets finished_at."""
    history_dir = tmp_path / "history"
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "_now_iso", lambda: "2026-03-28 10:00:00")

    config = SimpleNamespace(
        task="Build feature X",
        task_id="MRC-1",
        runner="codex",
        model="auto",
        effort="auto",
        target_branch="main",
        service="acquiring",
        namespace="u1",
        tags=["go"],
        extra_params={},
        first_role="architect",
        last_role="qa_stand",
        profile="test-profile",
    )

    state = PipelineState.create(
        task_id="MRC-1",
        task_text="Build feature X",
        selected_runner="codex",
        run_id="test-run-123",
    )
    state.status = "running"
    state.stage_attempts = []  # no attempts

    # Initial save
    history.save_run(config, state)
    entries = history.load_history(profile="test-profile")
    assert len(entries) == 1
    assert entries[0]["status"] == "running"

    # Simulate completion after some time
    monkeypatch.setattr(history, "_now_iso", lambda: "2026-03-28 10:05:00")
    state.status = "completed"
    state.stage_attempts = [
        {
            "stage": "architect",
            "attempt_number": 1,
            "in_snapshot": {"task": "Build feature X"},
            "out_snapshot": {"plan": "..."},
            "selected_rule": {"stage": "developer", "default": True},
            "next_stage": "developer",
        },
        {
            "stage": "developer",
            "attempt_number": 1,
            "in_snapshot": {"task": "Build feature X"},
            "out_snapshot": {"code": "..."},
            "selected_rule": {"stage": "test_developer", "default": True},
            "next_stage": "test_developer",
        },
    ]

    history.save_run(config, state)

    entries = history.load_history(profile="test-profile")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["status"] == "completed"
    assert entry["finished_at"] == "2026-03-28 10:05:00"
    assert len(entry["attempts"]) == 2
    assert entry["attempts"][0]["stage"] == "architect"
    assert entry["attempts"][1]["stage"] == "developer"


def test_profile_scoping_isolates_entries(tmp_path, monkeypatch) -> None:
    """Entries for different profiles go to separate files."""
    history_dir = tmp_path / "history"
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(history, "_now_iso", lambda: "2026-03-28 10:00:00")

    def make_config(profile: str):
        return SimpleNamespace(
            task="Test",
            task_id="T-1",
            runner="codex",
            model="auto",
            effort="auto",
            target_branch="main",
            service="svc",
            namespace="ns",
            tags=[],
            extra_params={},
            first_role="",
            last_role="",
            profile=profile,
        )

    state1 = PipelineState.create("T-1", "Test", "codex", run_id="run-1")
    state1.status = "completed"
    history.save_run(make_config("profile-a"), state1)

    state2 = PipelineState.create("T-1", "Test", "codex", run_id="run-2")
    state2.status = "completed"
    history.save_run(make_config("profile-b"), state2)

    # Load each profile separately
    entries_a = history.load_history(profile="profile-a")
    entries_b = history.load_history(profile="profile-b")
    assert len(entries_a) == 1 and entries_a[0]["run_id"] == "run-1"
    assert len(entries_b) == 1 and entries_b[0]["run_id"] == "run-2"

    # Load all profiles combined
    all_entries = history.load_history(profile=None)
    assert len(all_entries) == 2
    ids = [e["run_id"] for e in all_entries]
    assert "run-1" in ids and "run-2" in ids


def test_load_history_returns_empty_if_no_file(tmp_path, monkeypatch) -> None:
    history_dir = tmp_path / "history"
    monkeypatch.setattr(history, "HISTORY_DIR", history_dir)
    entries = history.load_history(profile="nonexistent")
    assert entries == []

