import sqlite3
from pathlib import Path

from hive_mind.maintenance.historical_outbox import archive_historical_outbox


def _init_outbox(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE capture_outbox (
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
    conn.executemany(
        """
        INSERT INTO capture_outbox (
            id, dedupe_key, provider, session_id, occurred_at, payload,
            attempts, next_retry_at, last_error, created_at,
            delivered_at, dead_letter_at, claim_owner, claim_until
        ) VALUES (?, ?, ?, ?, ?, '{}', ?, 0, ?, 0, ?, ?, NULL, NULL)
        """,
        [
            (1, "a", "codex", "s1", "2026-07-12T00:00:00+00:00", 0, "", None, None),
            (2, "b", "copilot", "s2", "2026-07-13T00:00:00+00:00", 0, "", None, None),
            (3, "c", "codex", "s3", "2026-07-26T00:00:00+00:00", 1, "boom", None, None),
            (4, "d", "codex", "s4", "2026-07-26T00:00:00+00:00", 0, "", 1.0, None),
        ],
    )
    conn.commit()
    conn.close()


def test_historical_outbox_dry_run_counts_only_inert_rows_before_cutoff(tmp_path):
    db = tmp_path / "capture.db"
    _init_outbox(db)

    report = archive_historical_outbox(
        outbox_db=db,
        cutoff_occurred_at="2026-07-20T00:00:00+00:00",
        apply=False,
    )

    assert report.scanned == 4
    assert report.eligible == 2
    assert report.archived == 0
    assert dict(report.providers) == {"codex": 1, "copilot": 1}
    assert report.blocked_attempted == 1
    assert report.blocked_delivered == 1


def test_historical_outbox_apply_moves_rows_to_archive_and_deletes_live(tmp_path):
    db = tmp_path / "capture.db"
    _init_outbox(db)

    report = archive_historical_outbox(
        outbox_db=db,
        cutoff_occurred_at="2026-07-20T00:00:00+00:00",
        apply=True,
    )

    assert report.archived == 2

    conn = sqlite3.connect(db)
    live = conn.execute("SELECT COUNT(*) FROM capture_outbox").fetchone()[0]
    archived = conn.execute("SELECT COUNT(*) FROM capture_outbox_archive").fetchone()[0]
    live_ids = [row[0] for row in conn.execute("SELECT id FROM capture_outbox ORDER BY id").fetchall()]
    conn.close()

    assert archived == 2
    assert live == 2
    assert live_ids == [3, 4]
