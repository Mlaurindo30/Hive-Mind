from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "capture"
if str(CAPTURE) not in sys.path:
    sys.path.insert(0, str(CAPTURE))

from parsers import hermes


def _schema(connection: sqlite3.Connection) -> None:
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
        """
    )


def _session(
    connection: sqlite3.Connection,
    sid: str,
    source: str,
    started_at: float,
) -> None:
    connection.execute(
        "INSERT INTO sessions"
        " (id, source, model, started_at, cwd, git_branch, git_repo_root)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            sid,
            source,
            "test-model",
            started_at,
            r"D:\\Hive-Mind\\workspace",
            "feature/hermes-desktop",
            r"D:\\Hive-Mind",
        ),
    )


def _message(
    connection: sqlite3.Connection,
    sid: str,
    role: str,
    content: str | None,
    timestamp: float,
    *,
    active: int = 1,
) -> None:
    connection.execute(
        "INSERT INTO messages (session_id, role, content, timestamp, active)"
        " VALUES (?, ?, ?, ?, ?)",
        (sid, role, content, timestamp, active),
    )


def test_desktop_session_preserves_all_active_conversation_evidence(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(hermes.core, "SESSION_CUTOFF_MS", 0)
    database = tmp_path / "state.db"
    with sqlite3.connect(database) as connection:
        _schema(connection)
        _session(connection, "desktop-native-sid", "desktop", 100.0)
        _message(connection, "desktop-native-sid", "user", "[Note: model changed] First prompt", 101.0)
        _message(connection, "desktop-native-sid", "assistant", "First answer", 102.0)
        _message(connection, "desktop-native-sid", "tool", "tool output", 103.0)
        _message(connection, "desktop-native-sid", "user", "Second prompt", 104.0)
        _message(connection, "desktop-native-sid", "assistant", "Second answer", 105.0)
        _message(connection, "desktop-native-sid", "assistant", "   ", 106.0)
        _message(connection, "desktop-native-sid", "user", "inactive prompt", 107.0, active=0)

    sessions = hermes.parse(database)

    assert len(sessions) == 1
    session = sessions[0]
    assert session["sid"] == "desktop-native-sid"
    assert session["source"] == "desktop"
    assert session["surface"] == "desktop"
    assert session["cwd"] == r"D:\\Hive-Mind\\workspace"
    assert session["git_branch"] == "feature/hermes-desktop"
    assert session["git_repo_root"] == r"D:\\Hive-Mind"
    assert "project" not in session
    assert session["prompts"] == ["First prompt", "Second prompt"]
    assert [event["timestamp"] for event in session["prompt_events"]] == [101.0, 104.0]
    assert [turn["tool_response"] for turn in session["turns"]] == [
        "First answer",
        "Second answer",
    ]
    assert [turn["timestamp"] for turn in session["turns"]] == [102.0, 105.0]
    assert [message["role"] for message in session["messages"]] == [
        "user",
        "assistant",
        "tool",
        "user",
        "assistant",
    ]
    assert session["last"] == "Second answer"


def test_only_top_level_cli_and_desktop_sources_are_returned(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(hermes.core, "SESSION_CUTOFF_MS", 0)
    database = tmp_path / "state.db"
    with sqlite3.connect(database) as connection:
        _schema(connection)
        for index, source in enumerate(("cli", "desktop", "subagent", "cron", "internal")):
            sid = f"{source}-sid"
            _session(connection, sid, source, 200.0 + index)
            _message(connection, sid, "user", f"{source} prompt", 210.0 + index)
            _message(connection, sid, "assistant", f"{source} answer", 220.0 + index)

    sessions = hermes.parse(database)

    assert [(session["sid"], session["surface"]) for session in sessions] == [
        ("cli-sid", "cli"),
        ("desktop-sid", "desktop"),
    ]


def test_note_is_only_stripped_when_complete_leading_note_exists():
    assert hermes._strip_note("[Note: model changed] real prompt") == "real prompt"
    assert hermes._strip_note("[Note: incomplete real prompt") == "[Note: incomplete real prompt"
    assert hermes._strip_note("prefix [Note: keep] prompt") == "prefix [Note: keep] prompt"
