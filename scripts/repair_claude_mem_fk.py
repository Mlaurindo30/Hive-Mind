#!/usr/bin/env python3
"""Repair orphan claude-mem session references without deleting memories."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "claude-mem" / "data" / "claude-mem.db"


def backup_database(conn: sqlite3.Connection, db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups" / "fk-repair"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"claude-mem.before-fk-repair.{stamp}.db"
    target = sqlite3.connect(backup_path)
    try:
        conn.backup(target)
    finally:
        target.close()
    backup_path.chmod(0o600)
    return backup_path


def orphan_sessions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        WITH child_sessions AS (
            SELECT memory_session_id, project, created_at, created_at_epoch,
                   prompt_number
            FROM observations
            WHERE memory_session_id IS NOT NULL
            UNION ALL
            SELECT memory_session_id, project, created_at, created_at_epoch,
                   prompt_number
            FROM session_summaries
            WHERE memory_session_id IS NOT NULL
        )
        SELECT
            memory_session_id,
            COALESCE(MAX(NULLIF(project, '')), 'recovered-history') AS project,
            MIN(created_at) AS started_at,
            MIN(created_at_epoch) AS started_at_epoch,
            MAX(created_at) AS completed_at,
            MAX(created_at_epoch) AS completed_at_epoch,
            COALESCE(MAX(prompt_number), 0) AS prompt_counter
        FROM child_sessions
        WHERE memory_session_id NOT IN (
            SELECT memory_session_id FROM sdk_sessions
            WHERE memory_session_id IS NOT NULL
        )
        GROUP BY memory_session_id
        ORDER BY started_at_epoch
        """
    ).fetchall()


def repair(db_path: Path) -> tuple[int, Path | None]:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        before = conn.execute("PRAGMA foreign_key_check").fetchall()
        rows = orphan_sessions(conn)
        if not rows:
            return len(before), None

        backup_path = backup_database(conn, db_path)
        conn.execute("BEGIN IMMEDIATE")
        for row in rows:
            memory_id = row["memory_session_id"]
            platform = memory_id.split("-", 1)[0] if "-" in memory_id else "recovered"
            conn.execute(
                """
                INSERT INTO sdk_sessions (
                    content_session_id, memory_session_id, project,
                    platform_source, started_at, started_at_epoch,
                    completed_at, completed_at_epoch, status, prompt_counter,
                    custom_title
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?)
                """,
                (
                    f"recovered:{memory_id}",
                    memory_id,
                    row["project"],
                    platform,
                    row["started_at"],
                    row["started_at_epoch"],
                    row["completed_at"],
                    row["completed_at_epoch"],
                    row["prompt_counter"],
                    "Recovered historical session",
                ),
            )

        after = conn.execute("PRAGMA foreign_key_check").fetchall()
        if after:
            conn.rollback()
            raise RuntimeError(
                f"repair left {len(after)} foreign-key violations; backup={backup_path}"
            )
        conn.commit()
        return len(rows), backup_path
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    repaired, backup = repair(args.db.resolve())
    print(f"repaired_sessions={repaired}")
    if backup:
        print(f"backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
