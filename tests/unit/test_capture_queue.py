from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.capture.capture_events import ProviderEvent
from scripts.capture.capture_queue import CaptureQueue


def _event(
    session_id: str,
    event_id: str,
    content: str,
    *,
    occurred_at: datetime | None = None,
) -> ProviderEvent:
    return ProviderEvent.create(
        "codex",
        session_id,
        "prompt",
        content,
        event_id=event_id,
        occurred_at=occurred_at,
    )


def test_queue_survives_restart_and_deduplicates(tmp_path: Path) -> None:
    event = _event("session", "1", "unique")
    db_path = tmp_path / "capture.db"
    first_queue = CaptureQueue(db_path)

    assert first_queue.enqueue(event) is True
    assert first_queue.enqueue(event) is False
    first_queue.close()

    second_queue = CaptureQueue(db_path)
    try:
        assert [item.event.content for item in second_queue.pending(10)] == ["unique"]
    finally:
        second_queue.close()


def test_retry_does_not_block_other_sessions(tmp_path: Path) -> None:
    queue = CaptureQueue(tmp_path / "capture.db")
    try:
        blocked = _event("blocked", "1", "one")
        later_in_blocked_session = _event("blocked", "2", "two")
        ready = _event("ready", "3", "three")
        assert queue.enqueue(blocked)
        assert queue.enqueue(later_in_blocked_session)
        assert queue.enqueue(ready)

        blocked_item = queue.pending(1)[0]
        queue.mark_retry(blocked_item.id, "worker offline", retry_at=time.time() + 60)

        assert [item.event.session_id for item in queue.pending(10)] == ["ready"]
    finally:
        queue.close()


def test_pending_keeps_events_ordered_within_a_session(tmp_path: Path) -> None:
    queue = CaptureQueue(tmp_path / "capture.db")
    try:
        base = datetime(2026, 7, 9, tzinfo=timezone.utc)
        later = _event("ordered", "2", "second", occurred_at=base + timedelta(seconds=1))
        earlier = _event("ordered", "1", "first", occurred_at=base)
        assert queue.enqueue(later)
        assert queue.enqueue(earlier)

        assert [item.event.content for item in queue.pending(10)] == ["first"]
        queue.mark_delivered(queue.pending(1)[0].id)
        assert [item.event.content for item in queue.pending(10)] == ["second"]
    finally:
        queue.close()


def test_matching_session_ids_from_different_providers_do_not_block_each_other(tmp_path: Path) -> None:
    queue = CaptureQueue(tmp_path / "capture.db")
    try:
        blocked = ProviderEvent.create("codex", "shared", "prompt", "one", event_id="1")
        ready = ProviderEvent.create("antigravity", "shared", "prompt", "two", event_id="2")
        assert queue.enqueue(blocked)
        assert queue.enqueue(ready)

        queue.mark_retry(queue.pending(1)[0].id, "worker offline", retry_at=time.time() + 60)

        assert [item.event.provider for item in queue.pending(10)] == ["antigravity"]
    finally:
        queue.close()


def test_retry_dead_letter_and_health_reflect_queue_state(tmp_path: Path) -> None:
    queue = CaptureQueue(tmp_path / "capture.db")
    try:
        event = _event("session", "1", "retry me")
        assert queue.enqueue(event)
        item = queue.pending(1)[0]

        queue.mark_retry(item.id, "temporary failure", retry_at=time.time() - 1)
        retried = queue.pending(1)[0]
        assert retried.attempts == 1
        assert retried.last_error == "temporary failure"

        queue.move_dead_letter(retried.id, "permanent failure")
        assert queue.pending(10) == []
        assert queue.health() == {
            "pending": 0,
            "retrying": 0,
            "delivered": 0,
            "dead_letter": 1,
        }
    finally:
        queue.close()
