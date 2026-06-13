"""
Unit tests for core/database.py

Strategy:
- ensure_migrations: tested with in-memory SQLite connections, no patching needed.
- get_connection: monkeypatched DB_PATH to a tmp file so tests do not touch hive_mind.db.
- execute_insert: exercised against in-memory DB to validate UUID injection and table whitelist.
- generate_uuid: pure logic, no I/O.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.database import (
    add_observation,
    ensure_migrations,
    execute_insert,
    generate_uuid,
    serialize_f32,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_observations_table(conn, include_uuid=False, include_source_machine=False):
    """Create the observations table optionally pre-including migration columns."""
    cols = [
        "id TEXT PRIMARY KEY",
        "session_id TEXT",
        "project TEXT",
        "type TEXT",
        "title TEXT",
        "content TEXT",
        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        "neuron_id TEXT",
        "archived INTEGER DEFAULT 0",
        "metadata JSON",
    ]
    if include_uuid:
        cols.append("uuid TEXT")
    if include_source_machine:
        cols.append("source_machine TEXT")

    conn.execute(f"CREATE TABLE observations ({', '.join(cols)})")
    conn.commit()


# ---------------------------------------------------------------------------
# ensure_migrations tests
# ---------------------------------------------------------------------------

class TestEnsureMigrations:

    def test_ensure_migrations_adds_uuid_column(self):
        """should add uuid column when observations table lacks it"""
        conn = sqlite3.connect(":memory:")
        _make_observations_table(conn)

        ensure_migrations(conn)

        cols = [row[1] for row in conn.execute("PRAGMA table_info(observations)")]
        assert "uuid" in cols, "ensure_migrations must add the uuid column"

    def test_ensure_migrations_adds_source_machine_column(self):
        """should add source_machine column when observations table lacks it"""
        conn = sqlite3.connect(":memory:")
        _make_observations_table(conn)

        ensure_migrations(conn)

        cols = [row[1] for row in conn.execute("PRAGMA table_info(observations)")]
        assert "source_machine" in cols, "ensure_migrations must add the source_machine column"

    def test_ensure_migrations_adds_archived_column(self):
        """should add archived column when observations table lacks it"""
        conn = sqlite3.connect(":memory:")
        # Build table WITHOUT archived to simulate very old schema
        conn.execute("""
            CREATE TABLE observations (
                id TEXT PRIMARY KEY,
                title TEXT,
                content TEXT,
                metadata JSON
            )
        """)
        conn.commit()

        ensure_migrations(conn)

        cols = [row[1] for row in conn.execute("PRAGMA table_info(observations)")]
        assert "archived" in cols, "ensure_migrations must add the archived column"

    def test_ensure_migrations_idempotent(self):
        """should not raise when called twice on the same connection"""
        conn = sqlite3.connect(":memory:")
        _make_observations_table(conn)

        ensure_migrations(conn)
        # Second call must not throw OperationalError or any other exception
        ensure_migrations(conn)

        cols = [row[1] for row in conn.execute("PRAGMA table_info(observations)")]
        uuid_count = cols.count("uuid")
        assert uuid_count == 1, "uuid column must appear exactly once after two migrations"

    def test_ensure_migrations_idempotent_source_machine(self):
        """should not duplicate source_machine column when called twice"""
        conn = sqlite3.connect(":memory:")
        _make_observations_table(conn)

        ensure_migrations(conn)
        ensure_migrations(conn)

        cols = [row[1] for row in conn.execute("PRAGMA table_info(observations)")]
        assert cols.count("source_machine") == 1

    def test_ensure_migrations_when_columns_already_exist(self):
        """should not raise when uuid and source_machine already exist in schema"""
        conn = sqlite3.connect(":memory:")
        _make_observations_table(conn, include_uuid=True, include_source_machine=True)

        # Must not raise even though columns already exist
        ensure_migrations(conn)

        cols = [row[1] for row in conn.execute("PRAGMA table_info(observations)")]
        assert "uuid" in cols
        assert "source_machine" in cols

    def test_ensure_migrations_creates_archived_index(self):
        """should create idx_observations_archived index"""
        conn = sqlite3.connect(":memory:")
        _make_observations_table(conn)

        ensure_migrations(conn)

        indices = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='observations'"
        ).fetchall()
        index_names = [row[0] for row in indices]
        assert "idx_observations_archived" in index_names

    def test_ensure_migrations_adds_intent_memory_schema(self):
        conn = sqlite3.connect(":memory:")
        _make_observations_table(conn)

        ensure_migrations(conn)

        cols = {row[1] for row in conn.execute("PRAGMA table_info(observations)")}
        assert {"goal_id", "why", "intent_source"} <= cols
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='goals'"
        ).fetchone()


def test_add_observation_persists_intent_fields(monkeypatch, tmp_path):
    import core.database as db_module

    db_path = tmp_path / "intent.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _make_observations_table(conn)
    ensure_migrations(conn)
    conn.close()

    def _connect():
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(db_module, "get_connection", _connect)

    observation_id = add_observation(
        "Production gate",
        "Finish P0",
        goal_id="goal-1",
        why="Make deployment safe",
        intent_source="user",
    )

    check = _connect()
    row = check.execute(
        "SELECT goal_id, why, intent_source FROM observations WHERE id=?",
        (observation_id,),
    ).fetchone()
    assert tuple(row) == ("goal-1", "Make deployment safe", "user")
    check.close()


# ---------------------------------------------------------------------------
# get_connection tests
# ---------------------------------------------------------------------------

class TestGetConnection:

    def test_get_connection_returns_sqlite_connection(self, tmp_path, monkeypatch):
        """should return a valid sqlite3.Connection object"""
        import core.database as db_module
        tmp_db = str(tmp_path / "test_hive.db")
        monkeypatch.setattr(db_module, "DB_PATH", tmp_db)

        from core.database import get_connection
        conn = get_connection()
        try:
            assert isinstance(conn, sqlite3.Connection), "get_connection must return a sqlite3.Connection"
        finally:
            conn.close()

    def test_get_connection_row_factory_is_row(self, tmp_path, monkeypatch):
        """should configure row_factory as sqlite3.Row for dict-like access"""
        import core.database as db_module
        tmp_db = str(tmp_path / "row_factory_test.db")
        monkeypatch.setattr(db_module, "DB_PATH", tmp_db)

        from core.database import get_connection
        conn = get_connection()
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# execute_insert tests
# ---------------------------------------------------------------------------

class TestExecuteInsert:

    def _conn_with_table(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE observations (
                id TEXT PRIMARY KEY,
                title TEXT,
                content TEXT,
                type TEXT,
                session_id TEXT,
                project TEXT,
                neuron_id TEXT,
                archived INTEGER DEFAULT 0,
                metadata JSON,
                created_at TEXT
            )
        """)
        conn.commit()
        return conn

    def test_execute_insert_auto_generates_uuid_when_id_missing(self):
        """should inject a UUID when the data dict has no id key"""
        conn = self._conn_with_table()
        row_id = execute_insert(conn, "observations", {
            "title": "Test",
            "content": "Body",
            "type": "note",
        })
        conn.commit()

        assert row_id is not None
        assert len(row_id) == 36, "Auto-generated id should be a UUID (36 chars)"
        result = conn.execute("SELECT id FROM observations").fetchone()
        assert result["id"] == row_id

    def test_execute_insert_uses_provided_id(self):
        """should use the caller-supplied id rather than generating a new UUID"""
        conn = self._conn_with_table()
        execute_insert(conn, "observations", {
            "id": "my-custom-id",
            "title": "Custom",
            "content": "Body",
            "type": "note",
        })
        conn.commit()

        result = conn.execute("SELECT id FROM observations").fetchone()
        assert result["id"] == "my-custom-id"

    def test_execute_insert_rejects_disallowed_table(self):
        """should raise ValueError when the table name is not in the whitelist"""
        conn = sqlite3.connect(":memory:")
        with pytest.raises(ValueError, match="Tabela não permitida"):
            execute_insert(conn, "secret_table", {"title": "x"})

    def test_execute_insert_rejects_invalid_column_name(self):
        """should raise ValueError when a column name is not a valid Python identifier"""
        conn = self._conn_with_table()
        with pytest.raises(ValueError, match="Nome de coluna inválido"):
            execute_insert(conn, "observations", {"title; DROP TABLE observations": "evil"})


# ---------------------------------------------------------------------------
# generate_uuid tests
# ---------------------------------------------------------------------------

class TestGenerateUuid:

    def test_generate_uuid_returns_string(self):
        """should return a string"""
        result = generate_uuid()
        assert isinstance(result, str)

    def test_generate_uuid_is_36_chars(self):
        """should return a 36-character UUID v4 string"""
        result = generate_uuid()
        assert len(result) == 36

    def test_generate_uuid_is_unique(self):
        """should return different values on consecutive calls"""
        uuid1 = generate_uuid()
        uuid2 = generate_uuid()
        assert uuid1 != uuid2


# ---------------------------------------------------------------------------
# serialize_f32 tests
# ---------------------------------------------------------------------------

class TestSerializeF32:

    def test_serialize_f32_returns_bytes(self):
        """should return bytes for a float list"""
        result = serialize_f32([0.1, 0.2, 0.3])
        assert isinstance(result, bytes)

    def test_serialize_f32_length_is_4_bytes_per_float(self):
        """should encode 4 bytes per float value"""
        vec = [1.0, 2.0, 3.0, 4.0]
        result = serialize_f32(vec)
        assert len(result) == 4 * len(vec)
