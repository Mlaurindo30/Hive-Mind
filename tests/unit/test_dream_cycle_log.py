"""Memória Viva M9 (doc 08, §14.4-P2) — telemetria de sobrevivência do dream cycle.

Testa contra SQLite REAL (in-memory), não mock (R1/R5 do §14): a migração cria
`dream_cycle_log` idempotentemente e a tabela aceita as linhas que o ciclo grava
(incluindo os ended_reason: ok / failed / empty / BUDGET_EXHAUSTED / error).
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.database import ensure_migrations

# Schema mínimo exigido por ensure_migrations (sem sqlite-vec/FTS).
_BASE_DDL = """
CREATE TABLE observations (
    id TEXT PRIMARY KEY,
    archived INTEGER DEFAULT 0,
    metadata JSON
);
CREATE TABLE neurons (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    type TEXT NOT NULL,
    updated_at TIMESTAMP
);
"""


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_BASE_DDL)
    return conn


def test_migration_creates_dream_cycle_log():
    conn = _make_conn()
    ensure_migrations(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(dream_cycle_log)")]
    for expected in (
        "id", "started_at", "ended_at", "duration_s",
        "observations_processed", "ambiguities_processed", "ended_reason",
    ):
        assert expected in cols, f"coluna {expected} ausente em dream_cycle_log"
    conn.close()


def test_migration_idempotent():
    conn = _make_conn()
    ensure_migrations(conn)
    ensure_migrations(conn)  # 2ª passada não pode levantar
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='dream_cycle_log'"
    ).fetchone()[0]
    assert n == 1
    conn.close()


def test_index_on_started_at_exists():
    conn = _make_conn()
    ensure_migrations(conn)
    idx = [r[1] for r in conn.execute("PRAGMA index_list(dream_cycle_log)")]
    assert any("started" in name for name in idx), f"índice de started_at ausente: {idx}"
    conn.close()


def test_insert_row_roundtrip():
    """A tabela aceita uma linha de ciclo e o M9 (duration) é recuperável."""
    conn = _make_conn()
    ensure_migrations(conn)
    conn.execute(
        """INSERT INTO dream_cycle_log
           (started_at, ended_at, duration_s, observations_processed,
            ambiguities_processed, ended_reason)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("2026-06-18T03:00:00", "2026-06-18T03:00:42", 42.0, 30, 3, "ok"),
    )
    conn.commit()
    row = conn.execute(
        "SELECT duration_s, observations_processed, ended_reason FROM dream_cycle_log"
    ).fetchone()
    assert row["duration_s"] == 42.0
    assert row["observations_processed"] == 30
    assert row["ended_reason"] == "ok"
    conn.close()


def test_accepts_all_ended_reasons():
    conn = _make_conn()
    ensure_migrations(conn)
    for reason in ("ok", "failed", "empty", "BUDGET_EXHAUSTED", "error"):
        conn.execute(
            "INSERT INTO dream_cycle_log (started_at, ended_reason) VALUES (?, ?)",
            ("2026-06-18T03:00:00", reason),
        )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM dream_cycle_log").fetchone()[0]
    assert count == 5
    conn.close()
