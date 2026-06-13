import sqlite3

from scripts.materialize_operational_state import (
    CAUSE_ID,
    EFFECT_ID,
    GOAL_ID,
    materialize,
)


def test_materialize_is_idempotent_and_links_intent_to_causality():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE neurons (
            id TEXT PRIMARY KEY, label TEXT NOT NULL, type TEXT NOT NULL,
            source_file TEXT, content TEXT, hash TEXT, metadata TEXT,
            community INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP, visibility TEXT DEFAULT 'private',
            indexed_at TEXT
        );
        CREATE TABLE observations (
            id TEXT PRIMARY KEY, session_id TEXT, project TEXT, type TEXT,
            title TEXT, content TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            neuron_id TEXT, archived INTEGER DEFAULT 0, metadata TEXT
        );
        """
    )

    materialize(conn)
    materialize(conn)

    assert conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM causal_edges").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM neurons").fetchone()[0] == 2
    row = conn.execute(
        "SELECT goal_id, why, intent_source FROM observations"
    ).fetchone()
    assert row["goal_id"] == GOAL_ID
    assert row["why"]
    assert row["intent_source"] == "user"
    edge = conn.execute(
        "SELECT cause_neuron_id, effect_neuron_id FROM causal_edges"
    ).fetchone()
    assert tuple(edge) == (CAUSE_ID, EFFECT_ID)
