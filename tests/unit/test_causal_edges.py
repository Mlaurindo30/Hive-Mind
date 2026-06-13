"""Sprint C3 — tests for causal_edges table and get_causal_neighbors helper."""
import sqlite3
import sys
import os

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.database import ensure_migrations, get_causal_neighbors

# ---------------------------------------------------------------------------
# Minimal schema required by ensure_migrations (no sqlite-vec, no FTS)
# ---------------------------------------------------------------------------
_BASE_DDL = """
CREATE TABLE observations (
    id TEXT PRIMARY KEY,
    archived INTEGER DEFAULT 0,
    metadata JSON
);
CREATE TABLE neurons (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    type TEXT NOT NULL
);
"""


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_BASE_DDL)
    return conn


# ---------------------------------------------------------------------------
# Test 1 — migration creates causal_edges table
# ---------------------------------------------------------------------------
def test_migration_creates_table():
    conn = _make_conn()
    ensure_migrations(conn)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(causal_edges)")]
    assert "id" in columns
    assert "cause_neuron_id" in columns
    assert "effect_neuron_id" in columns
    assert "confidence" in columns
    conn.close()


# ---------------------------------------------------------------------------
# Test 2 — migration is idempotent (calling twice must not raise)
# ---------------------------------------------------------------------------
def test_migration_idempotent():
    conn = _make_conn()
    ensure_migrations(conn)
    ensure_migrations(conn)  # second call must not raise
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _insert_neuron(conn, neuron_id: str):
    conn.execute(
        "INSERT INTO neurons(id, label, type) VALUES (?, ?, ?)",
        (neuron_id, neuron_id, "concept"),
    )


def _insert_edge(conn, cause: str, effect: str, label: str = "causes", confidence: float = 1.0):
    import uuid
    conn.execute(
        "INSERT INTO causal_edges(id, cause_neuron_id, effect_neuron_id, label, confidence) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), cause, effect, label, confidence),
    )


# ---------------------------------------------------------------------------
# Test 3 — one-hop neighbors
# ---------------------------------------------------------------------------
def test_get_causal_neighbors_one_hop():
    conn = _make_conn()
    ensure_migrations(conn)

    _insert_neuron(conn, "A")
    _insert_neuron(conn, "B")
    _insert_edge(conn, "A", "B", label="triggers", confidence=0.9)
    conn.commit()

    neighbors = get_causal_neighbors(conn, "A", hops=1)
    assert len(neighbors) == 1
    assert neighbors[0]["neuron_id"] == "B"
    assert neighbors[0]["label"] == "triggers"
    assert abs(neighbors[0]["confidence"] - 0.9) < 1e-9
    conn.close()


# ---------------------------------------------------------------------------
# Test 4 — two-hop neighbors (chained A→B→C)
# ---------------------------------------------------------------------------
def test_get_causal_neighbors_two_hops():
    conn = _make_conn()
    ensure_migrations(conn)

    _insert_neuron(conn, "A")
    _insert_neuron(conn, "B")
    _insert_neuron(conn, "C")
    _insert_edge(conn, "A", "B")
    _insert_edge(conn, "B", "C")
    conn.commit()

    neighbors = get_causal_neighbors(conn, "A", hops=2)
    ids = {n["neuron_id"] for n in neighbors}
    assert "B" in ids, "1-hop neighbor B should be present"
    assert "C" in ids, "2-hop neighbor C should be present"
    conn.close()
