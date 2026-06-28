"""Unit — migração CRR-safe workspace/federação (core/database, B1/B6).

Sem serviço: valida o helper `alter_table_crr_safe` (caminho tabela-normal) e
`migrate_workspace_and_federation` (colunas, default, idempotência, tabela
ausente). O caminho CRR (crsql_begin_alter) é exercido nos testes reais com
HIVE_CRDT_SYNC; aqui cobrimos a lógica determinística.
"""
import sqlite3

import pytest

import core.database as db

_TABLES = [
    "neurons", "observations", "synapses", "goals", "document_memories",
    "visual_memories", "ambiguities", "causal_edges", "vault",
]


def _mini_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    for t in _TABLES:
        conn.execute(f"CREATE TABLE {t} (id TEXT PRIMARY KEY, content TEXT)")
    return conn


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_workspace_id_added_to_all_tables():
    conn = _mini_db()
    db.migrate_workspace_and_federation(conn)
    for t in _TABLES:
        assert "workspace_id" in _cols(conn, t), f"{t} sem workspace_id"


def test_workspace_default_is_default():
    conn = _mini_db()
    db.migrate_workspace_and_federation(conn)
    conn.execute("INSERT INTO neurons (id, content) VALUES ('n1', 'x')")
    val = conn.execute("SELECT workspace_id FROM neurons WHERE id='n1'").fetchone()[0]
    assert val == "default"


def test_neurons_federation_and_embedding_columns():
    conn = _mini_db()
    db.migrate_workspace_and_federation(conn)
    cols = _cols(conn, "neurons")
    assert {"origin_instance", "origin_signature",
            "embedding_model", "embedding_dim"} <= cols


def test_idempotent():
    conn = _mini_db()
    db.migrate_workspace_and_federation(conn)
    db.migrate_workspace_and_federation(conn)  # não pode levantar
    assert "workspace_id" in _cols(conn, "neurons")


def test_skips_missing_tables():
    conn = sqlite3.connect(":memory:")  # nenhuma tabela
    db.migrate_workspace_and_federation(conn)  # não pode levantar


def test_alter_table_crr_safe_plain_table():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (id TEXT)")
    db.alter_table_crr_safe(conn, "t", "ws TEXT NOT NULL DEFAULT 'default'")
    assert "ws" in _cols(conn, "t")


def test_ensure_migrations_uses_crr_safe_alter_for_legacy_columns():
    """Todos ADD COLUMN de ensure_migrations devem respeitar tabela CRR."""
    calls = []
    conn = sqlite3.connect(":memory:")
    conn.create_function("crsql_begin_alter", 1, lambda table: calls.append(("begin", table)) or 1)
    conn.create_function("crsql_commit_alter", 1, lambda table: calls.append(("commit", table)) or 1)
    conn.executescript("""
        CREATE TABLE observations (
            id TEXT PRIMARY KEY,
            metadata JSON
        );
        CREATE TABLE observations__crsql_clock (id TEXT);
        CREATE TABLE neurons (
            id TEXT PRIMARY KEY,
            label TEXT,
            type TEXT,
            updated_at TIMESTAMP
        );
        CREATE TABLE neurons__crsql_clock (id TEXT);
    """)

    db.ensure_migrations(conn)

    assert "uuid" in _cols(conn, "observations")
    assert "topic" in _cols(conn, "neurons")
    assert ("begin", "observations") in calls
    assert ("commit", "observations") in calls
    assert ("begin", "neurons") in calls
    assert ("commit", "neurons") in calls


def test_index_created():
    conn = _mini_db()
    db.migrate_workspace_and_federation(conn)
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_neurons_workspace" in idx


def test_backup_created_on_real_file(tmp_path):
    """B8: migração em DB-arquivo cria backup .pre-workspace uma vez."""
    p = tmp_path / "hive_mind.db"
    conn = sqlite3.connect(str(p))
    for t in _TABLES:
        conn.execute(f"CREATE TABLE {t} (id TEXT PRIMARY KEY, content TEXT)")
    conn.commit()
    db.migrate_workspace_and_federation(conn)
    conn.close()
    assert (tmp_path / "hive_mind.db.pre-workspace").exists()


def test_backup_skipped_in_memory():
    """:memory: não tem arquivo — migração roda sem backup, sem crash."""
    conn = _mini_db()
    db.migrate_workspace_and_federation(conn)
    assert "workspace_id" in _cols(conn, "neurons")


def _minimal_ensure_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE observations (
            id TEXT PRIMARY KEY,
            archived INTEGER DEFAULT 0,
            metadata JSON
        )
    """)
    conn.execute("CREATE TABLE neurons (id TEXT PRIMARY KEY, label TEXT, type TEXT)")
    return conn


def test_ensure_migrations_fails_closed_on_workspace_failure_by_default(monkeypatch):
    conn = _minimal_ensure_conn()

    def fail(_conn):
        raise sqlite3.OperationalError("boom")

    monkeypatch.delenv("HIVE_ALLOW_DEFERRED_MIGRATIONS", raising=False)
    monkeypatch.setattr(db, "migrate_workspace_and_federation", fail)
    with pytest.raises(RuntimeError, match="corrija a migração"):
        db.ensure_migrations(conn)


def test_ensure_migrations_deferred_requires_explicit_legacy_bypass(monkeypatch):
    conn = _minimal_ensure_conn()

    def fail(_conn):
        raise sqlite3.OperationalError("boom")

    monkeypatch.setenv("HIVE_ALLOW_DEFERRED_MIGRATIONS", "1")
    monkeypatch.setattr(db, "migrate_workspace_and_federation", fail)
    db.ensure_migrations(conn)  # bypass explícito para diagnóstico de DB legado
