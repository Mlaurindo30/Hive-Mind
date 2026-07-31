"""Controlled archival of inert historical capture_outbox rows."""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from datetime import datetime, timezone

from core.database import with_sqlite_retry
from hive_mind.maintenance.lock import MaintenanceLock


@dataclass(frozen=True)
class HistoricalOutboxReport:
    outbox_db: str
    apply: bool
    cutoff_occurred_at: str | None
    scanned: int = 0
    eligible: int = 0
    archived: int = 0
    providers: tuple[tuple[str, int], ...] = ()
    oldest_eligible: str | None = None
    newest_eligible: str | None = None
    blocked_attempted: int = 0
    blocked_delivered: int = 0
    blocked_dead_letter: int = 0
    blocked_recent: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _open_rw(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 60000;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass
    return conn


def archive_historical_outbox(
    *,
    outbox_db: str | Path,
    cutoff_occurred_at: str | None = None,
    apply: bool = False,
) -> HistoricalOutboxReport:
    path = Path(outbox_db)
    if not path.is_file():
        raise FileNotFoundError(path)

    ro = _open_ro(path)
    try:
        tables = {r[0] for r in ro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "capture_outbox" not in tables:
            return HistoricalOutboxReport(
                outbox_db=str(path),
                apply=apply,
                cutoff_occurred_at=cutoff_occurred_at,
            )
        where_parts = [
            "COALESCE(delivered_at, '') = ''",
            "COALESCE(dead_letter_at, '') = ''",
            "COALESCE(attempts, 0) = 0",
            "COALESCE(last_error, '') = ''",
        ]
        params: list[object] = []
        if cutoff_occurred_at:
            where_parts.append("occurred_at <= ?")
            params.append(cutoff_occurred_at)
        eligible_where = " AND ".join(where_parts)

        scanned = int(ro.execute("SELECT COUNT(*) FROM capture_outbox").fetchone()[0])
        eligible = int(
            ro.execute(f"SELECT COUNT(*) FROM capture_outbox WHERE {eligible_where}", params).fetchone()[0]
        )
        providers = tuple(
            (str(row[0]), int(row[1]))
            for row in ro.execute(
                f"SELECT provider, COUNT(*) FROM capture_outbox WHERE {eligible_where} "
                "GROUP BY provider ORDER BY 2 DESC",
                params,
            ).fetchall()
        )
        oldest = ro.execute(
            f"SELECT occurred_at FROM capture_outbox WHERE {eligible_where} "
            "ORDER BY occurred_at ASC LIMIT 1",
            params,
        ).fetchone()
        newest = ro.execute(
            f"SELECT occurred_at FROM capture_outbox WHERE {eligible_where} "
            "ORDER BY occurred_at DESC LIMIT 1",
            params,
        ).fetchone()
        blocked_attempted = int(
            ro.execute(
                "SELECT COUNT(*) FROM capture_outbox WHERE COALESCE(attempts, 0) > 0"
            ).fetchone()[0]
        )
        blocked_delivered = int(
            ro.execute(
                "SELECT COUNT(*) FROM capture_outbox WHERE delivered_at IS NOT NULL"
            ).fetchone()[0]
        )
        blocked_dead_letter = int(
            ro.execute(
                "SELECT COUNT(*) FROM capture_outbox WHERE dead_letter_at IS NOT NULL"
            ).fetchone()[0]
        )
        blocked_recent = scanned - eligible - blocked_attempted - blocked_delivered - blocked_dead_letter
    finally:
        ro.close()

    archived = 0
    if apply and eligible:
        lock_path = path.with_suffix(path.suffix + ".historical-archive.lock")
        with MaintenanceLock(lock_path):
            rw = _open_rw(path)
            try:
                rw.execute(
                    """
                    CREATE TABLE IF NOT EXISTS capture_outbox_archive (
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
                        claim_until REAL,
                        archived_at TEXT NOT NULL
                    )
                    """
                )

                def _write() -> None:
                    nonlocal archived
                    rw.execute("BEGIN IMMEDIATE")
                    archived_at = datetime.now(timezone.utc).isoformat()
                    where_parts_rw = [
                        "COALESCE(delivered_at, '') = ''",
                        "COALESCE(dead_letter_at, '') = ''",
                        "COALESCE(attempts, 0) = 0",
                        "COALESCE(last_error, '') = ''",
                    ]
                    params_rw: list[object] = []
                    if cutoff_occurred_at:
                        where_parts_rw.append("occurred_at <= ?")
                        params_rw.append(cutoff_occurred_at)
                    eligible_where_rw = " AND ".join(where_parts_rw)
                    rw.execute(
                        f"""
                        INSERT OR REPLACE INTO capture_outbox_archive (
                            id, dedupe_key, provider, session_id, occurred_at, payload,
                            attempts, next_retry_at, last_error, created_at,
                            delivered_at, dead_letter_at, claim_owner, claim_until, archived_at
                        )
                        SELECT
                            id, dedupe_key, provider, session_id, occurred_at, payload,
                            attempts, next_retry_at, last_error, created_at,
                            delivered_at, dead_letter_at, claim_owner, claim_until, ?
                        FROM capture_outbox
                        WHERE {eligible_where_rw}
                        """,
                        [archived_at, *params_rw],
                    )
                    archived = int(
                        rw.execute(
                            f"SELECT COUNT(*) FROM capture_outbox WHERE {eligible_where_rw}", params_rw
                        ).fetchone()[0]
                    )
                    rw.execute(
                        f"DELETE FROM capture_outbox WHERE {eligible_where_rw}",
                        params_rw,
                    )
                    rw.commit()

                with_sqlite_retry(_write, op_label="historical_outbox_archive")
            except Exception:
                rw.rollback()
                raise
            finally:
                rw.close()

    return HistoricalOutboxReport(
        outbox_db=str(path),
        apply=apply,
        cutoff_occurred_at=cutoff_occurred_at,
        scanned=scanned,
        eligible=eligible,
        archived=archived,
        providers=providers,
        oldest_eligible=oldest[0] if oldest else None,
        newest_eligible=newest[0] if newest else None,
        blocked_attempted=blocked_attempted,
        blocked_delivered=blocked_delivered,
        blocked_dead_letter=blocked_dead_letter,
        blocked_recent=blocked_recent,
    )
