from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "capture"
if str(CAPTURE) not in sys.path:
    sys.path.insert(0, str(CAPTURE))

from parsers import hermes


def test_wal_database_is_reopened_read_only_without_missing_desktop_commit(tmp_path):
    database = tmp_path / "Hermes state with spaces.db"
    writer = sqlite3.connect(database)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                model TEXT,
                started_at REAL NOT NULL,
                cwd TEXT,
                git_branch TEXT,
                git_repo_root TEXT
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                timestamp REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        writer.commit()
        writer.execute(
            "INSERT INTO sessions"
            " (id, source, model, started_at, cwd, git_branch, git_repo_root)"
            " VALUES (?, 'desktop', 'realistic-model', ?, ?, ?, ?)",
            ("wal-desktop-sid", 1000.0, r"C:\\Work\\Current", "main", r"C:\\Work\\Current"),
        )
        writer.executemany(
            "INSERT INTO messages (session_id, role, content, timestamp, active)"
            " VALUES ('wal-desktop-sid', ?, ?, ?, 1)",
            (
                ("user", "WAL prompt one", 1001.0),
                ("assistant", "WAL answer one", 1002.0),
                ("tool", "WAL tool interleave", 1003.0),
                ("user", "WAL prompt two", 1004.0),
                ("assistant", "WAL answer two", 1005.0),
            ),
        )
        writer.commit()
        assert database.with_name(database.name + "-wal").exists()

        before = database.stat().st_mtime_ns
        sessions = hermes.parse(database)
        after = database.stat().st_mtime_ns

        assert [session["sid"] for session in sessions] == ["wal-desktop-sid"]
        assert sessions[0]["prompts"] == ["WAL prompt one", "WAL prompt two"]
        assert sessions[0]["last"] == "WAL answer two"
        assert before == after
        assert writer.execute("PRAGMA query_only").fetchone()[0] == 0
    finally:
        writer.close()
