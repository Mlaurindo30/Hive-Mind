"""Durable SQLite outbox for normalized provider capture events."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Iterator

from scripts.capture.capture_events import ProviderEvent


@dataclass(frozen=True)
class QueueItem:
    """An event awaiting delivery, with its delivery state."""

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

    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
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
                    time.time(),
                ),
            )
            return result.rowcount == 1

    def pending(self, limit: int) -> list[QueueItem]:
        """Return ready events, preserving order among events in each session."""
        if limit <= 0:
            return []

        with self._lock:
            rows = self._connection.execute(
                """
                SELECT current.*
                FROM capture_outbox AS current
                WHERE current.delivered_at IS NULL
                  AND current.dead_letter_at IS NULL
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
                """,
                (time.time(), limit),
            ).fetchall()
        return [self._queue_item(row) for row in rows]

    def mark_delivered(self, item_id: int) -> None:
        """Mark a queued event as delivered."""
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE capture_outbox
                SET delivered_at = ?, last_error = NULL
                WHERE id = ? AND delivered_at IS NULL AND dead_letter_at IS NULL
                """,
                (time.time(), item_id),
            )

    def mark_retry(self, item_id: int, error: str, retry_at: float) -> None:
        """Record a failed delivery and make the event eligible at ``retry_at``."""
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE capture_outbox
                SET attempts = attempts + 1, last_error = ?, next_retry_at = ?
                WHERE id = ? AND delivered_at IS NULL AND dead_letter_at IS NULL
                """,
                (error, float(retry_at), item_id),
            )

    def move_dead_letter(self, item_id: int, error: str) -> None:
        """Stop retrying an event after a permanent delivery failure."""
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE capture_outbox
                SET dead_letter_at = ?, last_error = ?
                WHERE id = ? AND delivered_at IS NULL AND dead_letter_at IS NULL
                """,
                (time.time(), error, item_id),
            )

    def health(self) -> dict[str, int]:
        """Return delivery-state counts for monitoring."""
        now = time.time()
        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                    SUM(delivered_at IS NULL AND dead_letter_at IS NULL AND next_retry_at <= ?) AS pending,
                    SUM(delivered_at IS NULL AND dead_letter_at IS NULL AND next_retry_at > ?) AS retrying,
                    SUM(delivered_at IS NOT NULL) AS delivered,
                    SUM(dead_letter_at IS NOT NULL) AS dead_letter
                FROM capture_outbox
                """,
                (now, now),
            ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}

    def close(self) -> None:
        """Release the SQLite connection."""
        with self._lock:
            self._connection.close()

    def _initialize_schema(self) -> None:
        with self._transaction() as connection:
            connection.executescript(
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
                    dead_letter_at REAL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS capture_outbox_dedupe_key
                    ON capture_outbox(dedupe_key);
                CREATE INDEX IF NOT EXISTS capture_outbox_pending
                    ON capture_outbox(provider, session_id, occurred_at, id);
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
