"""Tests for automation state persistence."""

from __future__ import annotations

from pathlib import Path

from automation.state_store import AutomationState, AutomationStateStore


def test_state_store_returns_empty_state_when_missing(tmp_path: Path) -> None:
    """Missing state files should return the default in-memory state."""
    store = AutomationStateStore(tmp_path / "mail_job_state.json")

    state = store.load()

    assert state.last_success_at == ""
    assert state.processed_message_ids == []
    assert state.downloaded_attachment_hashes == []


def test_state_store_round_trips_completed_state(tmp_path: Path) -> None:
    """Saved state should load back without losing fields."""
    store = AutomationStateStore(tmp_path / "mail_job_state.json")
    state = AutomationState(
        last_attempt_at="2026-04-02T09:00:00",
        last_success_at="2026-04-02T09:05:00",
        processed_message_ids=["1001"],
        downloaded_attachment_hashes=["abc123"],
        last_task_summary={"downloaded": 2},
    )

    store.save(state)

    reloaded = store.load()
    assert reloaded.last_attempt_at == "2026-04-02T09:00:00"
    assert reloaded.last_success_at == "2026-04-02T09:05:00"
    assert reloaded.processed_message_ids == ["1001"]
    assert reloaded.downloaded_attachment_hashes == ["abc123"]
    assert reloaded.last_task_summary == {"downloaded": 2}


def test_state_store_preserves_success_cursor_on_failed_run(
    tmp_path: Path,
) -> None:
    """A failed run should not wipe the previous success cursor."""
    store = AutomationStateStore(tmp_path / "mail_job_state.json")
    store.save(
        AutomationState(
            last_attempt_at="2026-04-02T09:00:00",
            last_success_at="2026-04-02T09:05:00",
            processed_message_ids=["1001"],
            downloaded_attachment_hashes=["abc123"],
            last_task_summary={"downloaded": 2},
        )
    )

    store.save(
        AutomationState(
            last_attempt_at="2026-04-03T09:00:00",
            processed_message_ids=["1002"],
            downloaded_attachment_hashes=["def456"],
            last_task_summary={"downloaded": 0, "errors": 1},
        )
    )

    reloaded = store.load()
    assert reloaded.last_attempt_at == "2026-04-03T09:00:00"
    assert reloaded.last_success_at == "2026-04-02T09:05:00"
    assert reloaded.processed_message_ids == ["1002"]
    assert reloaded.downloaded_attachment_hashes == ["def456"]
    assert reloaded.last_task_summary == {"downloaded": 0, "errors": 1}
