"""Normalized event contract for provider capture sources."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json


class EventType(str, Enum):
    """Event categories accepted by the capture delivery pipeline."""

    SESSION_START = "session_start"
    PROMPT = "prompt"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    ASSISTANT = "assistant"
    SESSION_END = "session_end"


@dataclass(frozen=True)
class ProviderEvent:
    """An immutable, provider-neutral event ready for durable delivery."""

    provider: str
    session_id: str
    event_type: EventType
    content: str
    event_id: str
    occurred_at: str
    source_position: str | None = None

    def __post_init__(self) -> None:
        """Enforce the contract for direct dataclass construction too."""
        self._require_value("provider", self.provider)
        self._require_value("session_id", self.session_id)
        self._require_value("content", self.content)
        self._require_value("event_id", self.event_id)

        try:
            event_type = EventType(self.event_type)
        except ValueError as error:
            raise ValueError(f"event_type must be a valid EventType: {self.event_type!r}") from error

        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "occurred_at", self._normalize_utc_timestamp(self.occurred_at))
        object.__setattr__(self, "source_position", self._normalize_source_position(self.source_position))

    @classmethod
    def create(
        cls,
        provider: str,
        session_id: str,
        event_type: EventType | str,
        content: str,
        *,
        event_id: str | None = None,
        occurred_at: datetime | str | None = None,
        source_position: str | None = None,
    ) -> ProviderEvent:
        """Create a validated event with stable fallback identity."""
        cls._require_value("provider", provider)
        cls._require_value("session_id", session_id)
        cls._require_value("content", content)

        try:
            normalized_type = EventType(event_type)
        except ValueError as error:
            raise ValueError(f"event_type must be a valid EventType: {event_type!r}") from error

        if event_id is not None:
            cls._require_value("event_id", event_id)
        normalized_position = cls._normalize_source_position(source_position)
        resolved_id = event_id or cls._hash(
            {
                "provider": provider,
                "session_id": session_id,
                "event_type": normalized_type.value,
                "content": content,
                "source_position": normalized_position,
            }
        )

        return cls(
            provider=provider,
            session_id=session_id,
            event_type=normalized_type,
            content=content,
            event_id=resolved_id,
            occurred_at=cls._normalize_timestamp(occurred_at),
            source_position=normalized_position,
        )

    def dedupe_key(self) -> str:
        """Return a provider-scoped hash suitable for a unique outbox key."""
        return self._hash(
            {
                "provider": self.provider,
                "session_id": self.session_id,
                "event_type": self.event_type.value,
                "event_id": self.event_id,
            }
        )

    def as_payload(self) -> dict[str, str | None]:
        """Return the JSON-ready representation used by queue and sink layers."""
        return {
            "provider": self.provider,
            "session_id": self.session_id,
            "event_type": self.event_type.value,
            "content": self.content,
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
            "source_position": self.source_position,
        }

    @staticmethod
    def _require_value(field: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")

    @staticmethod
    def _normalize_timestamp(value: datetime | str | None) -> str:
        if value is None:
            timestamp = datetime.now(timezone.utc)
        elif isinstance(value, datetime):
            timestamp = value
        elif isinstance(value, str):
            try:
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError(f"occurred_at must be an ISO-8601 timestamp: {value!r}") from error
        else:
            raise ValueError("occurred_at must be a datetime, ISO-8601 string, or None")

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _normalize_utc_timestamp(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("occurred_at must be an ISO-8601 UTC string")
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"occurred_at must be an ISO-8601 timestamp: {value!r}") from error
        if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
            raise ValueError("occurred_at must be an ISO-8601 UTC timestamp")
        return timestamp.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _normalize_source_position(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("source_position must be a string or None")
        return value or None

    @staticmethod
    def _hash(value: dict[str, str | None]) -> str:
        canonical_json = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
