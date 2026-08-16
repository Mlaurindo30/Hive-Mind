"""Where an identity decision is kept between ingest and bridge (ADR-014).

The worker generates observations itself, so the envelope we post does not
survive into them — measured in M14-A. What does survive is the session id we
generate, reachable from an observation through a declared foreign key. So the
decision is written here, keyed by that id, before the post goes out; the
bridge looks it up instead of deciding again.

Two properties matter more than anything else here:

**Nothing is delivered without a recoverable decision.** The write happens
first. If it fails, the post does not happen at all — a delivered event whose
identity cannot be recovered is exactly the state this work exists to end.

**A contradiction is never resolved silently.** The same session arriving with
a different identity is a defect somewhere upstream, not a value to overwrite.
It goes to `QUARANTINED` and stops, because guessing which of two answers was
right is how the free-label era started.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 1

DEFAULT_FILENAME = "capture-identities.db"
_UNCLASSIFIED_PREFIX = "unclassified/"


class DeliveryState(str, Enum):
    PENDING = "PENDING"
    POSTED = "POSTED"
    OBSERVED = "OBSERVED"
    BRIDGED = "BRIDGED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


# What may follow what. A delivery only moves forward, except for retry
# (FAILED back to PENDING) — because a retry is a new attempt at the same
# decision, not a new decision.
ALLOWED_TRANSITIONS: dict[DeliveryState, frozenset[DeliveryState]] = {
    DeliveryState.PENDING: frozenset({DeliveryState.POSTED, DeliveryState.FAILED,
                                      DeliveryState.QUARANTINED}),
    DeliveryState.POSTED: frozenset({DeliveryState.OBSERVED, DeliveryState.FAILED,
                                     DeliveryState.QUARANTINED}),
    DeliveryState.OBSERVED: frozenset({DeliveryState.BRIDGED,
                                       DeliveryState.QUARANTINED}),
    DeliveryState.BRIDGED: frozenset({DeliveryState.QUARANTINED}),
    DeliveryState.FAILED: frozenset({DeliveryState.PENDING, DeliveryState.POSTED,
                                     DeliveryState.QUARANTINED}),
    # Terminal on purpose: a quarantined conflict is resolved by a human
    # looking at it, not by the next write.
    DeliveryState.QUARANTINED: frozenset(),
}


class IdentityStoreError(RuntimeError):
    """Base for every refusal this store makes."""


class IdentityConflict(IdentityStoreError):
    """The same session, a different identity. Never resolved by overwriting."""

    def __init__(self, content_session_id: str, stored: str, incoming: str) -> None:
        self.content_session_id = content_session_id
        self.stored = stored
        self.incoming = incoming
        super().__init__(
            f"session {content_session_id[:24]}… already decided as {stored!r}; "
            f"refusing to replace it with {incoming!r}"
        )


class InvalidTransition(IdentityStoreError):
    def __init__(self, current: DeliveryState, target: DeliveryState) -> None:
        super().__init__(f"cannot move from {current.value} to {target.value}")


_STATE_ORDER: dict[DeliveryState, int] = {
    DeliveryState.PENDING: 0,
    DeliveryState.POSTED: 1,
    DeliveryState.OBSERVED: 2,
    DeliveryState.BRIDGED: 3,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical_json(envelope: dict[str, Any]) -> str:
    """A stable serialisation, so the hash of one decision is one value."""
    return json.dumps(envelope, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def identity_hash(envelope: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(envelope).encode("utf-8")).hexdigest()


def _is_unclassified(project_id: str | None) -> bool:
    return str(project_id or "").startswith(_UNCLASSIFIED_PREFIX)


def _identity_score(envelope: dict[str, Any]) -> int:
    """Richer identities win when the project id is already the same.

    Multiple capture surfaces may describe the same session with the same
    canonical project id but different envelope detail (for example, a
    transcript-only source without workspace data and a later SQLite source
    with concrete workspace/repository fields). That is not a contradiction.
    """
    score = 0
    for key in ("workspace_root", "repository_root", "git_common_dir", "branch"):
        if envelope.get(key):
            score += 1
    if envelope.get("resolution_method") and envelope.get("resolution_method") != "unclassified_provider":
        score += 1
    return score


@dataclass(frozen=True)
class IdentityDecision:
    """One decision, as it was made at ingest."""

    content_session_id: str
    provider: str
    surface: str
    project_id: str
    project_name: str
    identity: dict[str, Any]
    identity_hash: str
    raw_project_label: Optional[str]
    delivery_state: DeliveryState
    post_attempts: int
    last_error: Optional[str]
    created_at: str
    updated_at: str
    posted_at: Optional[str] = None
    observed_at: Optional[str] = None
    bridged_at: Optional[str] = None
    expires_at: Optional[str] = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS capture_identity_decisions (
    content_session_id TEXT PRIMARY KEY,
    provider           TEXT NOT NULL,
    surface            TEXT NOT NULL,
    project_id         TEXT NOT NULL,
    project_name       TEXT NOT NULL,
    identity_json      TEXT NOT NULL,
    identity_hash      TEXT NOT NULL,
    raw_project_label  TEXT,
    delivery_state     TEXT NOT NULL,
    post_attempts      INTEGER NOT NULL DEFAULT 0,
    last_error         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    posted_at          TEXT,
    observed_at        TEXT,
    bridged_at         TEXT,
    expires_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_capture_identity_state
    ON capture_identity_decisions(delivery_state);
CREATE INDEX IF NOT EXISTS idx_capture_identity_project
    ON capture_identity_decisions(project_id);
"""


def default_path(state_dir: Optional[Path] = None) -> Path:
    """Where the store lives when nobody says otherwise.

    Never inside a Claude Mem directory: this database belongs to Hive-Mind,
    and mixing it into a third party's data directory is how
    `~/.claude-mem/capture.db` came to look like the Claude Mem store when it
    was actually an abandoned outbox.
    """
    if state_dir is not None:
        return Path(state_dir) / DEFAULT_FILENAME
    override = os.environ.get("HIVE_CAPTURE_IDENTITY_DB")
    if override:
        return Path(override)
    try:
        from hive_mind.project import resolve_project_root

        root = resolve_project_root()
    except Exception:
        root = Path.cwd()
    return root / ".hive-mind" / "state" / DEFAULT_FILENAME


class IdentityStore:
    """SQLite-backed, WAL, safe across restarts and concurrent writers."""

    def __init__(self, path: Optional[Path] = None, *,
                 state_dir: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else default_path(state_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path), timeout=30,
                                           isolation_level=None,
                                           check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA busy_timeout=15000")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection_lock = threading.RLock()
        self._migrate()

    # -- lifecycle ---------------------------------------------------------
    def _migrate(self) -> None:
        # `executescript` commits implicitly, so it cannot run inside an
        # explicit transaction — the COMMIT afterwards would find none open.
        # It is idempotent (every statement is IF NOT EXISTS), so a crash
        # between it and the version row leaves a store that opens cleanly.
        self._connection.executescript(_SCHEMA)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT version FROM schema_version").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,))
            elif row["version"] > SCHEMA_VERSION:
                raise IdentityStoreError(
                    f"store at {self.path} is schema v{row['version']}; this "
                    f"code understands v{SCHEMA_VERSION}"
                )

    def close(self) -> None:
        with self._connection_lock:
            self._connection.close()

    def __enter__(self) -> "IdentityStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    class _Transaction:
        def __init__(self, connection: sqlite3.Connection,
                     lock: threading.RLock) -> None:
            self._connection = connection
            self._lock = lock

        def __enter__(self):
            self._lock.acquire()
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                return self._connection
            except BaseException:
                self._lock.release()
                raise

        def __exit__(self, exc_type, exc, tb):
            try:
                if exc_type is None:
                    self._connection.execute("COMMIT")
                else:
                    self._connection.execute("ROLLBACK")
                return False
            finally:
                self._lock.release()

    def _transaction(self) -> "_Transaction":
        return IdentityStore._Transaction(
            self._connection, self._connection_lock
        )

    # -- reads -------------------------------------------------------------
    def get(self, content_session_id: str) -> Optional[IdentityDecision]:
        with self._connection_lock:
            row = self._connection.execute(
                "SELECT * FROM capture_identity_decisions"
                " WHERE content_session_id=?",
                (content_session_id,)).fetchone()
        return self._decision(row) if row else None

    @staticmethod
    def _decision(row: sqlite3.Row) -> IdentityDecision:
        return IdentityDecision(
            content_session_id=row["content_session_id"],
            provider=row["provider"],
            surface=row["surface"],
            project_id=row["project_id"],
            project_name=row["project_name"],
            identity=json.loads(row["identity_json"]),
            identity_hash=row["identity_hash"],
            raw_project_label=row["raw_project_label"],
            delivery_state=DeliveryState(row["delivery_state"]),
            post_attempts=row["post_attempts"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            posted_at=row["posted_at"],
            observed_at=row["observed_at"],
            bridged_at=row["bridged_at"],
            expires_at=row["expires_at"],
        )

    def counts(self) -> dict[str, int]:
        """State histogram, for health. Never exposes content."""
        with self._connection_lock:
            rows = self._connection.execute(
                "SELECT delivery_state, COUNT(*) n"
                " FROM capture_identity_decisions GROUP BY delivery_state"
            ).fetchall()
            counted = {state.value: 0 for state in DeliveryState}
            counted.update({row["delivery_state"]: row["n"] for row in rows})
        return counted

    # -- writes ------------------------------------------------------------
    def record_pending(self, *, content_session_id: str, provider: str,
                       surface: str, project_id: str, project_name: str,
                       identity: dict[str, Any],
                       raw_project_label: Optional[str] = None
                       ) -> IdentityDecision:
        """Write the decision. Idempotent for the same identity; refuses another.

        Called before the post. Re-running the same session must not create a
        second row or move `created_at` — a retry is another attempt at one
        decision, not a new one.
        """
        if not content_session_id:
            raise IdentityStoreError("content_session_id is required")
        digest = identity_hash(identity)
        now = _now()
        conflict: Optional[IdentityConflict] = None

        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM capture_identity_decisions WHERE content_session_id=?",
                (content_session_id,)).fetchone()

            if row is None:
                connection.execute(
                    "INSERT INTO capture_identity_decisions ("
                    " content_session_id, provider, surface, project_id,"
                    " project_name, identity_json, identity_hash,"
                    " raw_project_label, delivery_state, post_attempts,"
                    " created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,0,?,?)",
                    (content_session_id, provider, surface, project_id,
                     project_name, canonical_json(identity), digest,
                     raw_project_label, DeliveryState.PENDING.value, now, now))
            elif (
                _is_unclassified(row["project_id"])
                and not _is_unclassified(project_id)
            ):
                # A previous degraded fallback is not authoritative when a
                # later replay brings concrete workspace evidence for the same
                # session. Promote the better answer and let delivery restart.
                connection.execute(
                    "UPDATE capture_identity_decisions SET provider=?, surface=?,"
                    " project_id=?, project_name=?, identity_json=?,"
                    " identity_hash=?, raw_project_label=?, delivery_state=?,"
                    " updated_at=?, last_error=? WHERE content_session_id=?",
                    (provider, surface, project_id, project_name,
                     canonical_json(identity), digest, raw_project_label,
                     DeliveryState.PENDING.value, now, None,
                     content_session_id))
            elif row["project_id"] == project_id and _is_unclassified(project_id):
                stored_identity = json.loads(row["identity_json"])
                preferred = identity
                preferred_digest = digest
                preferred_provider = provider
                preferred_surface = surface
                preferred_label = raw_project_label
                if _identity_score(stored_identity) > _identity_score(identity):
                    preferred = stored_identity
                    preferred_digest = row["identity_hash"]
                    preferred_provider = row["provider"]
                    preferred_surface = row["surface"]
                    preferred_label = row["raw_project_label"]
                should_reopen = (
                    row["delivery_state"] == DeliveryState.QUARANTINED.value
                    and row["last_error"] == "identity conflict on the same content_session_id"
                )
                if (
                    row["identity_hash"] != preferred_digest
                    or row["provider"] != preferred_provider
                    or row["surface"] != preferred_surface
                    or row["raw_project_label"] != preferred_label
                    or should_reopen
                ):
                    connection.execute(
                        "UPDATE capture_identity_decisions SET provider=?, surface=?,"
                        " identity_json=?, identity_hash=?, raw_project_label=?,"
                        " delivery_state=?, updated_at=?, last_error=?"
                        " WHERE content_session_id=?",
                        (preferred_provider, preferred_surface,
                         canonical_json(preferred), preferred_digest,
                         preferred_label, DeliveryState.PENDING.value, now,
                         None, content_session_id)
                    )
            elif row["project_id"] == project_id and not _is_unclassified(project_id):
                stored_identity = json.loads(row["identity_json"])
                if _identity_score(identity) > _identity_score(stored_identity):
                    connection.execute(
                        "UPDATE capture_identity_decisions SET provider=?, surface=?,"
                        " identity_json=?, identity_hash=?, raw_project_label=?,"
                        " delivery_state=?, updated_at=?, last_error=?"
                        " WHERE content_session_id=?",
                        (provider, surface, canonical_json(identity), digest,
                         raw_project_label, DeliveryState.PENDING.value, now,
                         None, content_session_id)
                    )
            elif row["identity_hash"] != digest or row["project_id"] != project_id:
                connection.execute(
                    "UPDATE capture_identity_decisions SET delivery_state=?,"
                    " updated_at=?, last_error=? WHERE content_session_id=?",
                    (DeliveryState.QUARANTINED.value, now,
                     "identity conflict on the same content_session_id",
                     content_session_id))
                # Recorded here, raised after the commit. Raising inside the
                # transaction rolled the quarantine back, leaving the conflict
                # detected and unrecorded — the worst of both.
                conflict = IdentityConflict(content_session_id,
                                            row["project_id"], project_id)
            elif (
                row["delivery_state"] == DeliveryState.QUARANTINED.value
                and row["last_error"] == "identity conflict on the same content_session_id"
            ):
                # If a later replay lands on the exact same recorded identity,
                # the transient contradiction has disappeared. Leaving the row
                # terminal would wedge capture permanently for a session whose
                # stable answer is now clear again.
                connection.execute(
                    "UPDATE capture_identity_decisions SET delivery_state=?,"
                    " updated_at=?, last_error=? WHERE content_session_id=?",
                    (DeliveryState.PENDING.value, now, None, content_session_id)
                )

        if conflict is not None:
            raise conflict

        decision = self.get(content_session_id)
        assert decision is not None
        return decision

    def _advance(self, content_session_id: str, target: DeliveryState, *,
                 column: Optional[str] = None,
                 error: Optional[str] = None,
                 count_attempt: bool = False) -> IdentityDecision:
        now = _now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT delivery_state, post_attempts FROM"
                " capture_identity_decisions WHERE content_session_id=?",
                (content_session_id,)).fetchone()
            if row is None:
                raise IdentityStoreError(
                    f"no decision recorded for {content_session_id[:24]}…")
            current = DeliveryState(row["delivery_state"])
            effective_target = target
            if current is target:
                pass  # idempotent
            elif (
                current in _STATE_ORDER
                and target in _STATE_ORDER
                and _STATE_ORDER[current] > _STATE_ORDER[target]
            ):
                effective_target = current  # monotonic replay; keep furthest state
            elif target not in ALLOWED_TRANSITIONS[current]:
                raise InvalidTransition(current, target)

            sets = ["delivery_state=?", "updated_at=?"]
            values: list[Any] = [effective_target.value, now]
            if column:
                sets.append(f"{column}=COALESCE({column}, ?)")
                values.append(now)
            if error is not None:
                sets.append("last_error=?")
                values.append(error[:500])
            if count_attempt:
                sets.append("post_attempts=post_attempts+1")
            values.append(content_session_id)
            connection.execute(
                f"UPDATE capture_identity_decisions SET {', '.join(sets)}"
                " WHERE content_session_id=?", values)

        decision = self.get(content_session_id)
        assert decision is not None
        return decision

    def mark_posted(self, content_session_id: str) -> IdentityDecision:
        return self._advance(content_session_id, DeliveryState.POSTED,
                             column="posted_at", count_attempt=True)

    def mark_failed(self, content_session_id: str, error: str) -> IdentityDecision:
        return self._advance(content_session_id, DeliveryState.FAILED,
                             error=_sanitise(error), count_attempt=True)

    def mark_observed(self, content_session_id: str) -> IdentityDecision:
        return self._advance(content_session_id, DeliveryState.OBSERVED,
                             column="observed_at")

    def mark_bridged(self, content_session_id: str) -> IdentityDecision:
        return self._advance(content_session_id, DeliveryState.BRIDGED,
                             column="bridged_at")

    def quarantine(self, content_session_id: str, reason: str) -> IdentityDecision:
        return self._advance(content_session_id, DeliveryState.QUARANTINED,
                             error=_sanitise(reason))

    # -- integrity ---------------------------------------------------------
    def verify(self) -> list[str]:
        """Problems found, as sentences. Empty means the store is sound."""
        problems: list[str] = []
        with self._connection_lock:
            integrity = self._connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
            if integrity != "ok":
                problems.append(f"integrity_check: {integrity}")
            for row in self._connection.execute("PRAGMA foreign_key_check"):
                problems.append(f"foreign_key_check: {tuple(row)}")
            for row in self._connection.execute(
                    "SELECT content_session_id, identity_json, identity_hash"
                    " FROM capture_identity_decisions"):
                try:
                    envelope = json.loads(row["identity_json"])
                except json.JSONDecodeError:
                    problems.append(
                        f"{row['content_session_id'][:24]}…: unreadable JSON"
                    )
                    continue
                if identity_hash(envelope) != row["identity_hash"]:
                    problems.append(
                        f"{row['content_session_id'][:24]}…:"
                        " identity hash mismatch"
                    )
        return problems


# Anything that looks like a credential is replaced before it is stored, so an
# error message cannot smuggle one into the database (SEC-001).
def _sanitise(message: str) -> str:
    import re

    # A scheme has to be consumed along with its value. `authorization: Bearer
    # sk-…` against a bare `\S+` matches "Bearer" and leaves the token
    # standing, which is what the first version of this did.
    message = re.sub(r"(?i)\b(bearer|basic|token)\s+\S+",
                     r"\1 <redacted>", message)
    message = re.sub(
        r"(?i)\b(api[_-]?key|key|token|secret|password|passwd|credential|"
        r"authorization)\b\s*[=:]\s*\S+",
        r"\1=<redacted>", message)
    # And a provider-shaped token on its own, named or not.
    return re.sub(r"\b(sk|pk|ghp|gho|xoxb)[-_][A-Za-z0-9_-]{8,}",
                  "<redacted>", message)
