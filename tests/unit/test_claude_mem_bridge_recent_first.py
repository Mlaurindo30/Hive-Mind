from __future__ import annotations

import sqlite3


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT NOT NULL,
            project TEXT NOT NULL,
            text TEXT,
            type TEXT NOT NULL,
            title TEXT,
            created_at TEXT NOT NULL,
            created_at_epoch INTEGER NOT NULL
        )
        """
    )
    return conn


def test_bridge_limit_prioritizes_recent_rows_without_source_filter():
    from core.knowledge.claude_mem_bridge import fetch_source_records

    conn = _conn()
    conn.executemany(
        """
        INSERT INTO observations(
            id, memory_session_id, project, text, type, title, created_at, created_at_epoch
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "m1", "old", "old text", "event", "old", "2026-07-27T17:00:00Z", 100),
            (2, "m2", "mid", "mid text", "event", "mid", "2026-07-27T17:10:00Z", 200),
            (3, "m3", "new", "new text", "event", "new", "2026-07-27T17:20:00Z", 300),
        ],
    )
    conn.commit()

    records = fetch_source_records(conn, limit=2, tables=("observations",))

    assert [record.source_id for record in records] == [
        "claude-mem:observations:2",
        "claude-mem:observations:3",
    ]


def test_bridge_source_id_filter_keeps_exact_selection():
    from core.knowledge.claude_mem_bridge import fetch_source_records

    conn = _conn()
    conn.executemany(
        """
        INSERT INTO observations(
            id, memory_session_id, project, text, type, title, created_at, created_at_epoch
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "m1", "old", "old text", "event", "old", "2026-07-27T17:00:00Z", 100),
            (2, "m2", "mid", "mid text", "event", "mid", "2026-07-27T17:10:00Z", 200),
            (3, "m3", "new", "new text", "event", "new", "2026-07-27T17:20:00Z", 300),
        ],
    )
    conn.commit()

    records = fetch_source_records(
        conn,
        limit=1,
        source_ids=["claude-mem:observations:1"],
        tables=("observations",),
    )

    assert [record.source_id for record in records] == ["claude-mem:observations:1"]
