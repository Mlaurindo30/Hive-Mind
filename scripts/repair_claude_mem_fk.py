#!/usr/bin/env python3
"""Repair orphan claude-mem session references without deleting memories."""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = Path.home() / ".claude-mem" / "claude-mem.db"


def _prune_backups(directory: Path, keep_last: int) -> None:
    if keep_last < 1:
        return
    backups = sorted(
        directory.glob("claude-mem.before-fk-repair.*.db"),
        key=lambda p: p.name,
    )
    for stale in backups[:-keep_last]:
        stale.unlink(missing_ok=True)


def backup_database(conn: sqlite3.Connection, db_path: Path, keep_last: int = 5) -> Path:
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
    _prune_backups(backup_dir, keep_last)
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


def repair(db_path: Path, keep_last: int = 5) -> tuple[int, Path | None]:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        before = conn.execute("PRAGMA foreign_key_check").fetchall()
        rows = orphan_sessions(conn)
        if not rows:
            return len(before), None

        backup_path = backup_database(conn, db_path, keep_last=keep_last)
        conn.execute("BEGIN IMMEDIATE")
        for row in rows:
            memory_id = row["memory_session_id"]
            # Deriva o provider do prefixo do memory_session_id (ex.: 'gemini-<uuid>'
            # → gemini). Se o prefixo for 8 chars hex, é o INÍCIO de um UUID puro
            # (sem provider) → rotula 'recovered' em vez de um hash sem sentido.
            prefix = memory_id.split("-", 1)[0] if "-" in memory_id else memory_id
            platform = "recovered" if re.fullmatch(r"[0-9a-f]{8}", prefix) else prefix
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
    parser.add_argument("--keep-backups", type=int, default=int(os.environ.get("HIVE_MIND_FK_REPAIR_BACKUPS_KEEP", "5")))
    args = parser.parse_args()
    repaired, backup = repair(args.db.resolve(), keep_last=args.keep_backups)
    print(f"repaired_sessions={repaired}")
    if backup:
        print(f"backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
