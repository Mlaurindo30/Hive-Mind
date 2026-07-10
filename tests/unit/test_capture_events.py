from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.capture.capture_events import EventType, ProviderEvent


def test_event_dedupe_is_stable_and_provider_scoped() -> None:
    a = ProviderEvent.create("codex", "s1", "prompt", "hello", event_id="7")
    b = ProviderEvent.create("codex", "s1", "prompt", "hello", event_id="7")
    c = ProviderEvent.create("antigravity", "s1", "prompt", "hello", event_id="7")

    assert a.dedupe_key() == b.dedupe_key()
    assert a.dedupe_key() != c.dedupe_key()


def test_missing_native_id_gets_deterministic_id() -> None:
    first = ProviderEvent.create("kimi", "s", "prompt", "hello", source_position="file:12")
    second = ProviderEvent.create("kimi", "s", "prompt", "hello", source_position="file:12")

    assert first.event_id == second.event_id


def test_create_normalizes_timestamp_and_serializes_payload() -> None:
    event = ProviderEvent.create(
        "codex",
        "session-1",
        EventType.PROMPT,
        "hello",
        event_id="native-1",
        occurred_at=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
        source_position="rollout.jsonl:12",
    )

    assert event.occurred_at == "2026-07-09T12:00:00+00:00"
    assert event.as_payload() == {
        "provider": "codex",
        "session_id": "session-1",
        "event_type": "prompt",
        "content": "hello",
        "event_id": "native-1",
        "occurred_at": "2026-07-09T12:00:00+00:00",
        "source_position": "rollout.jsonl:12",
    }


@pytest.mark.parametrize("field", ["provider", "session_id", "event_type", "content"])
def test_create_rejects_empty_required_values(field: str) -> None:
    values = {
        "provider": "codex",
        "session_id": "session-1",
        "event_type": "prompt",
        "content": "hello",
    }
    values[field] = ""

    with pytest.raises(ValueError, match=field):
        ProviderEvent.create(**values)
