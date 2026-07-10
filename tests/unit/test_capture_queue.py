from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.capture.capture_events import ProviderEvent
from scripts.capture.capture_queue import CaptureQueue


BASE_TIME = datetime(2026, 7, 9, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self, now: float = 1_783_555_200.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _event(
    session_id: str,
    event_id: str,
    content: str,
    *,
    provider: str = "codex",
    offset_seconds: int = 0,
) -> ProviderEvent:
    return ProviderEvent.create(
        provider,
        session_id,
        "prompt",
        content,
        event_id=event_id,
        occurred_at=BASE_TIME + timedelta(seconds=offset_seconds),
    )


def _queue(db_path: Path, clock: MutableClock) -> CaptureQueue:
    return CaptureQueue(db_path, clock=clock, lease_seconds=30)


def test_queue_survives_restart_and_deduplicates(tmp_path: Path) -> None:
    clock = MutableClock()
    event = _event("session", "1", "unique")
    db_path = tmp_path / "capture.db"
    first_queue = _queue(db_path, clock)

    assert first_queue.enqueue(event) is True
    assert first_queue.enqueue(event) is False
    first_queue.close()

    second_queue = _queue(db_path, clock)
    try:
        item = second_queue.pending(10)[0]
        assert item.event == event
    finally:
        second_queue.close()


def test_retry_does_not_block_other_sessions(tmp_path: Path) -> None:
    clock = MutableClock()
    queue = _queue(tmp_path / "capture.db", clock)
    try:
        blocked = _event("blocked", "1", "one")
        later_in_blocked_session = _event("blocked", "2", "two", offset_seconds=1)
        ready = _event("ready", "3", "three", offset_seconds=2)
        assert queue.enqueue(blocked)
        assert queue.enqueue(later_in_blocked_session)
        assert queue.enqueue(ready)

        blocked_item = queue.pending(1)[0]
        assert blocked_item.event == blocked
        queue.mark_retry(blocked_item.id, "worker offline", retry_at=clock() + 60)

        ready_item = queue.pending(10)[0]
        assert ready_item.event == ready
    finally:
        queue.close()


def test_pending_keeps_events_ordered_within_a_session(tmp_path: Path) -> None:
    clock = MutableClock()
    queue = _queue(tmp_path / "capture.db", clock)
    try:
        later = _event("ordered", "2", "second", offset_seconds=1)
        earlier = _event("ordered", "1", "first")
        assert queue.enqueue(later)
        assert queue.enqueue(earlier)

        first_item = queue.pending(10)[0]
        assert first_item.event == earlier
        queue.mark_delivered(first_item.id)
        assert queue.pending(10)[0].event == later
    finally:
        queue.close()


def test_matching_session_ids_from_different_providers_do_not_block_each_other(tmp_path: Path) -> None:
    clock = MutableClock()
    queue = _queue(tmp_path / "capture.db", clock)
    try:
        blocked = _event("shared", "1", "one", provider="codex")
        ready = _event("shared", "2", "two", provider="antigravity", offset_seconds=1)
        assert queue.enqueue(blocked)
        assert queue.enqueue(ready)

        blocked_item = queue.pending(1)[0]
        assert blocked_item.event == blocked
        queue.mark_retry(blocked_item.id, "worker offline", retry_at=clock() + 60)

        assert queue.pending(10)[0].event == ready
    finally:
        queue.close()


def test_pending_claims_an_item_until_lease_expires_or_worker_retries(tmp_path: Path) -> None:
    clock = MutableClock()
    db_path = tmp_path / "capture.db"
    first_queue = _queue(db_path, clock)
    second_queue = _queue(db_path, clock)
    try:
        event = _event("session", "1", "only once")
        assert first_queue.enqueue(event)

        first_claim = first_queue.pending(1)[0]
        assert first_claim.event == event
        assert second_queue.pending(1) == []

        clock.advance(31)
        second_claim = second_queue.pending(1)[0]
        assert second_claim.id == first_claim.id
        assert second_claim.event == event

        first_queue.mark_delivered(first_claim.id)
        assert second_queue.health()["claimed"] == 1
        second_queue.mark_retry(second_claim.id, "worker offline", retry_at=clock())
        assert first_queue.pending(1)[0].id == first_claim.id
    finally:
        first_queue.close()
        second_queue.close()


def test_initialization_reuses_a_complete_schema_idempotently(tmp_path: Path) -> None:
    clock = MutableClock()
    db_path = tmp_path / "capture.db"
    first_queue = _queue(db_path, clock)
    first_queue.close()

    second_queue = _queue(db_path, clock)
    try:
        assert second_queue.enqueue(_event("session", "1", "persisted"))
        with sqlite3.connect(db_path) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(capture_outbox)")
            }
        assert {"claim_owner", "claim_until", "delivered_at", "dead_letter_at"} <= columns
        assert second_queue.pending(1)[0].event.event_id == "1"
    finally:
        second_queue.close()


def test_health_separates_deliverable_claimed_retrying_and_blocked_items(tmp_path: Path) -> None:
    clock = MutableClock()
    queue = _queue(tmp_path / "capture.db", clock)
    try:
        retry_head = _event("ordered", "1", "head")
        blocked_successor = _event("ordered", "2", "successor", offset_seconds=1)
        claimed = _event("claimed", "3", "claimed", offset_seconds=2)
        deliverable = _event("ready", "4", "ready", offset_seconds=3)
        for event in (retry_head, blocked_successor, claimed, deliverable):
            assert queue.enqueue(event)

        head_item = queue.pending(1)[0]
        assert head_item.event == retry_head
        queue.mark_retry(head_item.id, "backoff", retry_at=clock() + 60)
        claimed_item = queue.pending(1)[0]
        assert claimed_item.event == claimed

        assert queue.health() == {
            "pending": 1,
            "claimed": 1,
            "retrying": 1,
            "blocked": 1,
            "delivered": 0,
            "dead_letter": 0,
        }
        assert queue.pending(10)[0].event == deliverable
    finally:
        queue.close()


def test_retry_dead_letter_and_health_reflect_queue_state(tmp_path: Path) -> None:
    clock = MutableClock()
    queue = _queue(tmp_path / "capture.db", clock)
    try:
        event = _event("session", "1", "retry me")
        assert queue.enqueue(event)
        item = queue.pending(1)[0]

        queue.mark_retry(item.id, "temporary failure", retry_at=clock())
        retried = queue.pending(1)[0]
        assert retried.attempts == 1
        assert retried.last_error == "temporary failure"

        queue.move_dead_letter(retried.id, "permanent failure")
        assert queue.pending(10) == []
        assert queue.health() == {
            "pending": 0,
            "claimed": 0,
            "retrying": 0,
            "blocked": 0,
            "delivered": 0,
            "dead_letter": 1,
        }
    finally:
        queue.close()
