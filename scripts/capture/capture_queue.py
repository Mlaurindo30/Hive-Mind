"""Durable SQLite outbox for normalized provider capture events."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Callable, Iterator
from uuid import uuid4

from scripts.capture.capture_events import ProviderEvent


@dataclass(frozen=True)
class QueueItem:
    """An event claimed by this queue instance for delivery."""

    id: int
    event: ProviderEvent
    attempts: int
    next_retry_at: float
    last_error: str | None
    created_at: float
    delivered_at: float | None
    dead_letter_at: float | None


class CaptureQueue:
    """Persist provider events until they are delivered or dead-lettered."""

    def __init__(
        self,
        db_path: Path,
        *,
        clock: Callable[[], float] = time.time,
        lease_seconds: float = 30.0,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")

        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._lease_seconds = float(lease_seconds)
        self._claim_owner = uuid4().hex
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(self._path),
            timeout=30,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute("PRAGMA busy_timeout=10000")
        self._initialize_schema()

    def enqueue(self, event: ProviderEvent) -> bool:
        """Store an event once, returning false when its dedupe key already exists."""
        with self._transaction() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO capture_outbox (
                    dedupe_key, provider, session_id, occurred_at, payload,
                    attempts, next_retry_at, created_at
                ) VALUES (?, ?, ?, ?, ?, 0, 0, ?)
                """,
                (
                    event.dedupe_key(),
                    event.provider,
                    event.session_id,
                    event.occurred_at,
                    json.dumps(event.as_payload(), separators=(",", ":"), sort_keys=True),
                    self._now(),
                ),
            )
            return result.rowcount == 1

    def pending(self, limit: int) -> list[QueueItem]:
        """Atomically claim and return ready session heads for this queue instance."""
        if limit <= 0:
            return []

        now = self._now()
        with self._transaction() as connection:
            rows = connection.execute(
                self._claimable_query(),
                (now, now, limit),
            ).fetchall()
            if not rows:
                return []

            item_ids = [int(row["id"]) for row in rows]
            placeholders = ", ".join("?" for _ in item_ids)
            connection.execute(
                f"""
                UPDATE capture_outbox
                SET claim_owner = ?, claim_until = ?
                WHERE id IN ({placeholders})
                """,
                (self._claim_owner, now + self._lease_seconds, *item_ids),
            )
        return [self._queue_item(row) for row in rows]

    def mark_delivered(self, item_id: int) -> bool:
        """Mark this queue instance's unexpired claim as delivered."""
        now = self._now()
        with self._transaction() as connection:
            result = connection.execute(
                """
                UPDATE capture_outbox
                SET delivered_at = ?, last_error = NULL,
                    claim_owner = NULL, claim_until = NULL
                WHERE id = ?
                  AND delivered_at IS NULL
                  AND dead_letter_at IS NULL
                  AND claim_owner = ?
                  AND claim_until > ?
                """,
                (now, item_id, self._claim_owner, now),
            )
            return result.rowcount == 1

    def mark_retry(self, item_id: int, error: str, retry_at: float) -> bool:
        """Record a failed delivery and release this queue instance's claim."""
        now = self._now()
        with self._transaction() as connection:
            result = connection.execute(
                """
                UPDATE capture_outbox
                SET attempts = attempts + 1, last_error = ?, next_retry_at = ?,
                    claim_owner = NULL, claim_until = NULL
                WHERE id = ?
                  AND delivered_at IS NULL
                  AND dead_letter_at IS NULL
                  AND claim_owner = ?
                  AND claim_until > ?
                """,
                (error, float(retry_at), item_id, self._claim_owner, now),
            )
            return result.rowcount == 1

    def move_dead_letter(self, item_id: int, error: str) -> bool:
        """Stop retrying this queue instance's claimed event after a permanent failure."""
        now = self._now()
        with self._transaction() as connection:
            result = connection.execute(
                """
                UPDATE capture_outbox
                SET dead_letter_at = ?, last_error = ?,
                    claim_owner = NULL, claim_until = NULL
                WHERE id = ?
                  AND delivered_at IS NULL
                  AND dead_letter_at IS NULL
                  AND claim_owner = ?
                  AND claim_until > ?
                """,
                (now, error, item_id, self._claim_owner, now),
            )
            return result.rowcount == 1

    def health(self) -> dict[str, int]:
        """Return mutually exclusive delivery-state counts for monitoring."""
        now = self._now()
        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                    SUM(
                        delivered_at IS NULL
                        AND dead_letter_at IS NULL
                        AND (claim_until IS NULL OR claim_until <= ?)
                        AND next_retry_at <= ?
                        AND NOT EXISTS (
                            SELECT 1
                            FROM capture_outbox AS predecessor
                            WHERE predecessor.provider = current.provider
                              AND predecessor.session_id = current.session_id
                              AND predecessor.delivered_at IS NULL
                              AND predecessor.dead_letter_at IS NULL
                              AND (
                                  predecessor.occurred_at < current.occurred_at
                                  OR (
                                      predecessor.occurred_at = current.occurred_at
                                      AND predecessor.id < current.id
                                  )
                              )
                        )
                    ) AS pending,
                    SUM(
                        delivered_at IS NULL
                        AND dead_letter_at IS NULL
                        AND claim_until > ?
                    ) AS claimed,
                    SUM(
                        delivered_at IS NULL
                        AND dead_letter_at IS NULL
                        AND (claim_until IS NULL OR claim_until <= ?)
                        AND next_retry_at > ?
                    ) AS retrying,
                    SUM(
                        delivered_at IS NULL
                        AND dead_letter_at IS NULL
                        AND (claim_until IS NULL OR claim_until <= ?)
                        AND next_retry_at <= ?
                        AND EXISTS (
                            SELECT 1
                            FROM capture_outbox AS predecessor
                            WHERE predecessor.provider = current.provider
                              AND predecessor.session_id = current.session_id
                              AND predecessor.delivered_at IS NULL
                              AND predecessor.dead_letter_at IS NULL
                              AND (
                                  predecessor.occurred_at < current.occurred_at
                                  OR (
                                      predecessor.occurred_at = current.occurred_at
                                      AND predecessor.id < current.id
                                  )
                              )
                        )
                    ) AS blocked,
                    SUM(delivered_at IS NOT NULL) AS delivered,
                    SUM(dead_letter_at IS NOT NULL) AS dead_letter
                FROM capture_outbox AS current
                """,
                (now, now, now, now, now, now, now),
            ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}

    def close(self) -> None:
        """Release the SQLite connection."""
        with self._lock:
            self._connection.close()

    def _initialize_schema(self) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS capture_outbox (
                    id INTEGER PRIMARY KEY,
                    dedupe_key TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    delivered_at REAL,
                    dead_letter_at REAL,
                    claim_owner TEXT,
                    claim_until REAL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(capture_outbox)")
            }
            if "claim_owner" not in columns:
                connection.execute("ALTER TABLE capture_outbox ADD COLUMN claim_owner TEXT")
            if "claim_until" not in columns:
                connection.execute("ALTER TABLE capture_outbox ADD COLUMN claim_until REAL")
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS capture_outbox_dedupe_key
                ON capture_outbox(dedupe_key)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS capture_outbox_pending
                ON capture_outbox(provider, session_id, occurred_at, id)
                """
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                yield self._connection
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    @staticmethod
    def _claimable_query() -> str:
        return """
            SELECT current.*
            FROM capture_outbox AS current
            WHERE current.delivered_at IS NULL
              AND current.dead_letter_at IS NULL
              AND (current.claim_until IS NULL OR current.claim_until <= ?)
              AND current.next_retry_at <= ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM capture_outbox AS predecessor
                  WHERE predecessor.provider = current.provider
                    AND predecessor.session_id = current.session_id
                    AND predecessor.delivered_at IS NULL
                    AND predecessor.dead_letter_at IS NULL
                    AND (
                        predecessor.occurred_at < current.occurred_at
                        OR (
                            predecessor.occurred_at = current.occurred_at
                            AND predecessor.id < current.id
                        )
                    )
              )
            ORDER BY current.occurred_at, current.id
            LIMIT ?
        """

    def _now(self) -> float:
        return float(self._clock())

    @staticmethod
    def _queue_item(row: sqlite3.Row) -> QueueItem:
        return QueueItem(
            id=int(row["id"]),
            event=ProviderEvent(**json.loads(row["payload"])),
            attempts=int(row["attempts"]),
            next_retry_at=float(row["next_retry_at"]),
            last_error=row["last_error"],
            created_at=float(row["created_at"]),
            delivered_at=row["delivered_at"],
            dead_letter_at=row["dead_letter_at"],
        )
