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
        "project": None,
        "cwd": None,
        "metadata": None,
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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", ""),
        ("session_id", ""),
        ("content", ""),
        ("event_id", ""),
        ("event_type", "not-an-event"),
        ("occurred_at", "2026-07-09T12:00:00+03:00"),
    ],
)
def test_direct_construction_rejects_invalid_contract_values(field: str, value: str) -> None:
    values: dict[str, EventType | str] = {
        "provider": "codex",
        "session_id": "session-1",
        "event_type": EventType.PROMPT,
        "content": "hello",
        "event_id": "native-1",
        "occurred_at": "2026-07-09T12:00:00+00:00",
    }
    values[field] = value

    with pytest.raises(ValueError, match=field):
        ProviderEvent(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("source_position", [12, True, object()])
def test_source_position_rejects_non_string_values(source_position: object) -> None:
    with pytest.raises(ValueError, match="source_position"):
        ProviderEvent.create("codex", "session-1", "prompt", "hello", source_position=source_position)  # type: ignore[arg-type]


def test_empty_source_position_normalizes_before_fallback_id() -> None:
    empty = ProviderEvent.create("codex", "session-1", "prompt", "hello", source_position="")
    absent = ProviderEvent.create("codex", "session-1", "prompt", "hello")

    assert empty.source_position is None
    assert empty.event_id == absent.event_id


def test_event_preserves_project_cwd_and_metadata() -> None:
    event = ProviderEvent.create(
        "hermes",
        "session-1",
        "tool_result",
        "ok",
        event_id="native-7",
        occurred_at="2026-07-17T12:00:00+00:00",
        project="my-project",
        cwd=r"C:\\work\\my-project",
        metadata={"tool_name": "Shell", "tool_input": {"command": "dir"}},
    )

    payload = event.as_payload()
    assert payload["project"] == "my-project"
    assert payload["cwd"] == r"C:\\work\\my-project"
    assert payload["metadata"] == {"tool_name": "Shell", "tool_input": {"command": "dir"}}


def test_old_queue_payload_without_context_remains_constructible() -> None:
    event = ProviderEvent(
        provider="codex",
        session_id="s",
        event_type="prompt",
        content="hello",
        event_id="1",
        occurred_at="2026-07-17T12:00:00+00:00",
    )
    assert event.project is None
    assert event.cwd is None
    assert event.metadata is None
