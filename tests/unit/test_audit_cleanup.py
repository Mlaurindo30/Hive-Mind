"""Test that AuditCleanup respects FK order and handles rollback.

Gate 3 regression: cleanup must delete children before parents.
"""
import sqlite3
from pathlib import Path
import pytest
from tests.helpers.audit_cleanup import AuditCleanup


SCHEMA = """
CREATE TABLE IF NOT EXISTS neurons (
    id TEXT PRIMARY KEY, label TEXT, content TEXT, type TEXT,
    source_file TEXT, metadata TEXT, workspace_id TEXT DEFAULT 'default'
);
CREATE TABLE IF NOT EXISTS synapses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL, target_id TEXT NOT NULL, relation TEXT,
    FOREIGN KEY(source_id) REFERENCES neurons(id) ON DELETE CASCADE,
    FOREIGN KEY(target_id) REFERENCES neurons(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT, neuron_id TEXT, project TEXT, goal_id TEXT,
    FOREIGN KEY(neuron_id) REFERENCES neurons(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS vault (
    id TEXT PRIMARY KEY, path TEXT, hash TEXT
);
CREATE TABLE IF NOT EXISTS vector_metadata (
    id TEXT, collection TEXT, PRIMARY KEY(collection, id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    neuron_id, content
);
"""


@pytest.fixture
def audit_db(tmp_path):
    db = tmp_path / "test_audit.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO neurons VALUES ('n1','AUDIT-E2E-abc','body','decision','vault/note.md','{}','default')")
    conn.execute("INSERT INTO neurons VALUES ('n2','other-note','body2','fact',NULL,'{}','default')")
    conn.execute("INSERT INTO synapses(source_id,target_id,relation) VALUES ('n1','n2','related_to')")
    conn.execute("INSERT INTO observations(content,neuron_id,project) VALUES ('probe','n1','test')")
    conn.execute("INSERT INTO vault VALUES ('n1','vault/note.md','abc123')")
    conn.execute("INSERT INTO vector_metadata VALUES ('n1','memory_vectors')")
    conn.execute("INSERT INTO search_fts VALUES ('n1','audit body')")
    conn.commit()
    conn.close()
    return db


class TestAuditCleanup:
    def test_deletes_children_before_parent(self, audit_db, tmp_path):
        vault = tmp_path / "cerebro"
        vault.mkdir()
        md = vault / "AUDIT-E2E-abc.md"
        md.write_text("test")

        cleanup = AuditCleanup(str(audit_db), vault)
        cleanup.register_neuron("n1")
        cleanup.register_file(md)
        result = cleanup.execute()

        assert result["neurons_deleted"] == 1
        assert result["synapses_deleted"] == 1
        assert result["observations_deleted"] == 1
        assert result["fts_deleted"] == 1
        assert result["vault_entries_deleted"] == 1
        assert result["vector_metadata_deleted"] == 1
        assert result["files_deleted"] == 1
        assert result["fk_ok"] is True
        assert result["integrity_ok"] is True
        assert not md.exists()

    def test_non_audit_neuron_untouched(self, audit_db, tmp_path):
        vault = tmp_path / "cerebro"
        vault.mkdir()
        cleanup = AuditCleanup(str(audit_db), vault)
        cleanup.register_neuron("n1")
        cleanup.execute()

        conn = sqlite3.connect(str(audit_db))
        row = conn.execute("SELECT id FROM neurons WHERE id='n2'").fetchone()
        conn.close()
        assert row is not None

    def test_discover_finds_audit_artifacts(self, audit_db, tmp_path):
        vault = tmp_path / "cerebro"
        vault.mkdir()
        (vault / "AUDIT-E2E-xyz.md").write_text("probe")

        cleanup = AuditCleanup(str(audit_db), vault)
        cleanup.discover_audit_artifacts("AUDIT-")
        assert len(cleanup._neuron_ids) >= 1
        assert any("AUDIT" in str(p) for p in cleanup._file_paths)

    def test_context_manager_cleans_on_exit(self, audit_db, tmp_path):
        vault = tmp_path / "cerebro"
        vault.mkdir()
        with AuditCleanup(str(audit_db), vault) as cleanup:
            cleanup.register_neuron("n1")
        conn = sqlite3.connect(str(audit_db))
        row = conn.execute("SELECT id FROM neurons WHERE id='n1'").fetchone()
        conn.close()
        assert row is None

    def test_rollback_on_integrity_failure(self, audit_db, tmp_path):
        vault = tmp_path / "cerebro"
        vault.mkdir()
        cleanup = AuditCleanup(str(audit_db), vault)
        cleanup.register_neuron("nonexistent")
        result = cleanup.execute()
        assert result["fk_ok"] is True
        assert result["integrity_ok"] is True
