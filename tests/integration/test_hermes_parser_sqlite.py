from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "capture"
if str(CAPTURE) not in sys.path:
    sys.path.insert(0, str(CAPTURE))

from parsers import hermes


def test_wal_database_is_reopened_read_only_without_missing_desktop_commit(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(hermes.core, "SESSION_CUTOFF_MS", 0)
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


def test_parser_to_capture_core_preserves_native_message_chronology(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(hermes.core, "SESSION_CUTOFF_MS", 0)
    database = tmp_path / "chronology.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
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
            INSERT INTO sessions
                (id, source, model, started_at, cwd, git_branch, git_repo_root)
            VALUES
                ('desktop-chronology', 'desktop', 'realistic-model', 100.0,
                 'D:\\Hive-Mind\\workspace', 'main', 'D:\\Hive-Mind');
            """
        )
        connection.executemany(
            "INSERT INTO messages (session_id, role, content, timestamp, active)"
            " VALUES ('desktop-chronology', ?, ?, ?, 1)",
            (
                ("user", "prompt one", 101.0),
                ("assistant", "answer one", 102.0),
                ("tool", "tool output", 103.0),
                ("user", "prompt two", 104.0),
                ("assistant", "answer two", 105.0),
            ),
        )

    session = hermes.parse(database)[0]
    identity = {
        "project_id": "hive-mind",
        "project_name": "Hive-Mind",
        "workspace_root": r"D:\Hive-Mind\workspace",
        "repository_root": r"D:\Hive-Mind",
        "repository_remote": "github.com/example/hive-mind",
        "git_common_dir": r"D:\Hive-Mind\.git",
        "worktree_name": None,
        "branch": "main",
        "provider": "hermes",
        "surface": "desktop",
        "resolution_method": "git_remote",
        "resolution_confidence": 1.0,
        "referenced_projects": [],
        "schema_version": 1,
    }
    session["project_identity"] = identity
    session["project_name"] = "Hive-Mind"

    calls = []

    def fake_post(path, payload):
        calls.append((path, payload))
        return {"stored": True}

    monkeypatch.setattr(hermes.core, "_post", fake_post)
    store = hermes.core.SeenStore(tmp_path / "chronology-seen.db")
    try:
        sent = hermes.core.ingest("hermes", session, store)
        expected_hashes = (
            hermes.core.content_hash(
                "desktop-chronology", "p", hermes.core._norm("prompt one")
            ),
            hermes.core.content_hash(
                "desktop-chronology", "p", hermes.core._norm("prompt two")
            ),
            hermes.core.content_hash(
                "desktop-chronology", "o", "Message", hermes.core._norm("answer one")
            ),
            hermes.core.content_hash(
                "desktop-chronology", "o", "Tool", hermes.core._norm("tool output")
            ),
            hermes.core.content_hash(
                "desktop-chronology", "o", "Message", hermes.core._norm("answer two")
            ),
        )
        assert all(
            store.contains("hermes", "desktop-chronology", content_hash)
            for content_hash in expected_hashes
        )
        delivered_call_count = len(calls)
        assert hermes.core.ingest("hermes", session, store) == 0
        assert len(calls) == delivered_call_count
    finally:
        store.close()

    assert [path for path, _ in calls] == [
        "/api/sessions/init",
        "/api/sessions/observations",
        "/api/sessions/observations",
        "/api/sessions/init",
        "/api/sessions/observations",
        "/api/sessions/summarize",
    ]
    assert sent == 3
    assert [payload.get("timestamp") for _, payload in calls] == [
        101.0,
        102.0,
        103.0,
        104.0,
        105.0,
        105.0,
    ]
    assert [payload.get("tool_name") for path, payload in calls if path.endswith("observations")] == [
        "Message",
        "Tool",
        "Message",
    ]
    assert calls[2][1]["tool_input"]["message_role"] == "tool"
    assert calls[2][1]["metadata"]["message_type"] == "tool"
    assert all(
        payload["metadata"]["project_identity"] == identity
        for _, payload in calls
    )
