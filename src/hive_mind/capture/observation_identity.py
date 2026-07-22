"""Recover the identity an observation was ingested under (M14, ADR-014).

The bridge does not decide what project an observation belongs to. It looks up
what the ingest already decided, through the relation M14-A measured:

    observations.memory_session_id
      -> sdk_sessions.memory_session_id     (declared FK, UNIQUE)
      -> sdk_sessions.content_session_id    (UNIQUE) = the sid we sent
      -> IdentityStore

That is the whole contract, and the reason it is a separate module: SQL
scattered through the bridge would eventually grow a "just this once" fallback
that reads `observations.project`, and the free-label era would restart from
there. Everything here either finds the recorded decision or says plainly that
it did not.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from hive_mind.capture.identity_store import (
    DeliveryState,
    IdentityStore,
    identity_hash,
)


class Origin(str, Enum):
    """Where a usable identity came from, or why there is none."""

    METADATA = "metadata"
    """The observation carried a valid envelope of its own."""

    REGISTRY = "registry"
    """Recovered from the decision the ingest recorded."""

    METADATA_AND_REGISTRY = "metadata+registry"
    """Both present and in agreement."""

    MISSING_SDK_SESSION = "missing_sdk_session"
    MISSING_CAPTURE_IDENTITY = "missing_capture_identity"
    INVALID_CAPTURE_IDENTITY = "invalid_capture_identity"
    CONFLICT = "identity_conflict"

    @property
    def usable(self) -> bool:
        return self in {Origin.METADATA, Origin.REGISTRY,
                        Origin.METADATA_AND_REGISTRY}

    @property
    def degraded(self) -> bool:
        return not self.usable


@dataclass(frozen=True)
class ObservationIdentity:
    """What the bridge may write, and where it came from."""

    origin: Origin
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    identity: Optional[dict[str, Any]] = None
    content_session_id: Optional[str] = None
    detail: str = ""

    @property
    def usable(self) -> bool:
        return self.origin.usable and bool(self.project_id)


REQUIRED_ENVELOPE_FIELDS = ("project_id", "project_name")


def _valid_envelope(envelope: Any) -> Optional[dict[str, Any]]:
    if not isinstance(envelope, dict):
        return None
    for field in REQUIRED_ENVELOPE_FIELDS:
        value = envelope.get(field)
        if not isinstance(value, str) or not value.strip():
            return None
    return envelope


def content_session_id_for(claude_mem: sqlite3.Connection,
                           memory_session_id: str) -> Optional[str]:
    """Follow the declared foreign key. Never parse the id's shape.

    `memory_session_id` happens to contain the sid as a substring today.
    Reading it that way would work until the worker changes its format, and
    would fail silently rather than loudly — so the join is the only path.
    """
    if not memory_session_id:
        return None
    try:
        row = claude_mem.execute(
            "SELECT content_session_id FROM sdk_sessions WHERE memory_session_id=?",
            (memory_session_id,)).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    value = row[0] if not isinstance(row, sqlite3.Row) else row["content_session_id"]
    return str(value).strip() or None if value else None


def resolve_capture_identity_for_observation(
    *,
    memory_session_id: str,
    claude_mem: sqlite3.Connection,
    identity_store: IdentityStore,
    metadata: Optional[dict[str, Any]] = None,
    mark_observed: bool = True,
) -> ObservationIdentity:
    """The identity for one observation. Recovered, never recomputed.

    `metadata` is whatever the observation carried. In practice it is empty —
    the worker generates observations itself and writes NULL (M14-A) — but a
    valid envelope is honoured when present, and checked against the registry
    when both exist.
    """
    envelope = _valid_envelope((metadata or {}).get("project_identity"))
    content_session_id = content_session_id_for(claude_mem, memory_session_id)

    if content_session_id is None:
        if envelope is not None:
            return ObservationIdentity(
                origin=Origin.METADATA,
                project_id=envelope["project_id"],
                project_name=envelope["project_name"],
                identity=envelope,
                detail="no sdk_session for this observation",
            )
        return ObservationIdentity(
            origin=Origin.MISSING_SDK_SESSION,
            detail=f"no sdk_session for memory_session_id {memory_session_id[:32]}…",
        )

    decision = identity_store.get(content_session_id)

    if decision is None:
        if envelope is not None:
            return ObservationIdentity(
                origin=Origin.METADATA,
                project_id=envelope["project_id"],
                project_name=envelope["project_name"],
                identity=envelope,
                content_session_id=content_session_id,
                detail="no recorded decision; used the observation's own envelope",
            )
        return ObservationIdentity(
            origin=Origin.MISSING_CAPTURE_IDENTITY,
            content_session_id=content_session_id,
            detail="no decision recorded for this session",
        )

    if identity_hash(decision.identity) != decision.identity_hash:
        return ObservationIdentity(
            origin=Origin.INVALID_CAPTURE_IDENTITY,
            content_session_id=content_session_id,
            detail="recorded decision failed its integrity hash",
        )

    if envelope is not None and envelope["project_id"] != decision.project_id:
        # Two answers for one observation. Quarantine and stop: choosing one
        # is exactly the guess this whole design exists to refuse. The write
        # is committed by the store before anything is raised or returned.
        identity_store.quarantine(
            content_session_id,
            "observation envelope disagrees with the recorded decision")
        return ObservationIdentity(
            origin=Origin.CONFLICT,
            content_session_id=content_session_id,
            detail=(f"envelope says {envelope['project_id']}, "
                    f"decision says {decision.project_id}"),
        )

    if mark_observed and decision.delivery_state is DeliveryState.POSTED:
        identity_store.mark_observed(content_session_id)

    return ObservationIdentity(
        origin=(Origin.METADATA_AND_REGISTRY if envelope is not None
                else Origin.REGISTRY),
        project_id=decision.project_id,
        project_name=decision.project_name,
        identity=decision.identity,
        content_session_id=content_session_id,
    )


def health_counters(identity_store: IdentityStore) -> dict[str, int]:
    """Registry state, named for health output. Never exposes content."""
    counted = identity_store.counts()
    return {
        "capture_identity_pending": counted["PENDING"],
        "capture_identity_posted": counted["POSTED"],
        "capture_identity_observed": counted["OBSERVED"],
        "capture_identity_bridged": counted["BRIDGED"],
        "capture_identity_failed": counted["FAILED"],
        "capture_identity_quarantined": counted["QUARANTINED"],
    }


def is_healthy(counters: dict[str, int]) -> bool:
    """A quarantined or failed decision is not a healthy registry.

    Reporting healthy while a conflict sits unresolved is how a broken
    pipeline stays broken: nobody looks at a green light.
    """
    return not (counters.get("capture_identity_quarantined", 0)
                or counters.get("capture_identity_failed", 0)
                or counters.get("capture_identity_conflicts", 0)
                or counters.get("capture_identity_missing_for_observation", 0))
