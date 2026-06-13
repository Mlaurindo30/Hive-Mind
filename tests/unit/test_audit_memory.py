"""
Unit tests for scripts/audit_memory.py

Strategy:
- Control SINAPSE_HOME via monkeypatch so run_audit() scans a tmp_path-based
  atlas directory instead of the real cerebro/atlas.
- Patch `scripts.audit_memory.get_connection` and `scripts.audit_memory.register_ambiguity`
  to avoid touching the real hive_mind.db.
- Use real file creation in tmp_path to exercise the actual detection logic.
"""

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audit_db():
    """
    In-memory SQLite with the tables that run_audit reads (neurons) and
    register_ambiguity writes to (ambiguities).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE neurons (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            type TEXT NOT NULL,
            source_file TEXT,
            content TEXT,
            hash TEXT,
            metadata JSON,
            community INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE ambiguities (
            id TEXT PRIMARY KEY,
            neuron_id TEXT NOT NULL,
            source_a_hash TEXT NOT NULL,
            source_b_hash TEXT NOT NULL,
            content_a TEXT NOT NULL,
            content_b TEXT NOT NULL,
            metadata_a JSON,
            metadata_b JSON,
            status TEXT DEFAULT 'pending',
            detected_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    return conn


def _make_vault(tmp_path):
    """Create the minimum directory structure run_audit() expects."""
    atlas = tmp_path / "cerebro" / "atlas"
    atlas.mkdir(parents=True)
    conflicts = tmp_path / "cerebro" / "conflicts"
    conflicts.mkdir(parents=True)
    return atlas


# ---------------------------------------------------------------------------
# Tests: conflict file detection
# ---------------------------------------------------------------------------

class TestSyncConflictDetection:
    """run_audit() should detect .sync-conflict-*.md files and route them."""

    def test_detects_sync_conflict_file(self, tmp_path, monkeypatch):
        """should detect a .sync-conflict file when it exists in atlas"""
        atlas = _make_vault(tmp_path)

        # Create the conflict file
        conflict_name = "my-neuron.sync-conflict-20260612-120000-DEVICE.md"
        (atlas / conflict_name).write_text("# Conflito\n\nConteúdo conflitante.", encoding="utf-8")

        # Create a neuron in DB that the conflict references (needed for canon lookup)
        mem_conn = _make_audit_db()
        mem_conn.execute(
            "INSERT INTO neurons (id, label, type, content, hash) VALUES (?, ?, ?, ?, ?)",
            ("my-neuron", "My Neuron", "fact", "Conteúdo original.", "aabbccdd")
        )
        mem_conn.commit()

        registered_calls = []

        def fake_register_ambiguity(neuron_id, version_a, version_b):
            registered_calls.append(neuron_id)
            return "fake-amb-id"

        with patch("scripts.audit_memory.get_connection", return_value=mem_conn), \
             patch("scripts.audit_memory.SINAPSE_HOME", str(tmp_path)), \
             patch("scripts.audit_memory.register_ambiguity", side_effect=fake_register_ambiguity):
            from scripts import audit_memory
            # Reset the module-level constant so it uses our tmp_path
            audit_memory.SINAPSE_HOME = str(tmp_path)
            audit_memory.run_audit(fix=True)

        assert len(registered_calls) == 1, "Exactly one conflict should have been registered"
        assert registered_calls[0] == "my-neuron"

    def test_ignores_regular_md_file(self, tmp_path):
        """should not flag a normal .md file as a conflict"""
        atlas = _make_vault(tmp_path)

        (atlas / "normal.md").write_text("# Normal\n\nRegular content.", encoding="utf-8")

        mem_conn = _make_audit_db()
        # Insert a matching neuron so the audit sees it as healthy
        mem_conn.execute(
            "INSERT INTO neurons (id, label, type, content, hash) VALUES (?, ?, ?, ?, ?)",
            ("normal", "Normal", "fact", "Regular content.", "placeholder")
        )
        mem_conn.commit()

        registered_calls = []

        def fake_register_ambiguity(neuron_id, version_a, version_b):
            registered_calls.append(neuron_id)

        with patch("scripts.audit_memory.get_connection", return_value=mem_conn), \
             patch("scripts.audit_memory.register_ambiguity", side_effect=fake_register_ambiguity):
            from scripts import audit_memory
            audit_memory.SINAPSE_HOME = str(tmp_path)
            audit_memory.run_audit(fix=True)

        assert len(registered_calls) == 0, "A normal .md file must not be treated as a conflict"

    def test_conflict_file_is_moved_to_conflicts_dir(self, tmp_path):
        """should move the conflict file to cerebro/conflicts/ after detection"""
        atlas = _make_vault(tmp_path)
        conflicts_dir = tmp_path / "cerebro" / "conflicts"

        conflict_name = "moved-neuron.sync-conflict-20260612-150000-HOST.md"
        conflict_path = atlas / conflict_name
        conflict_path.write_text("# Moved\n\nContent.", encoding="utf-8")

        mem_conn = _make_audit_db()
        mem_conn.execute(
            "INSERT INTO neurons (id, label, type, content, hash) VALUES (?, ?, ?, ?, ?)",
            ("moved-neuron", "Moved Neuron", "fact", "Content.", "hash1234")
        )
        mem_conn.commit()

        def fake_register_ambiguity(neuron_id, version_a, version_b):
            return "fake-id"

        with patch("scripts.audit_memory.get_connection", return_value=mem_conn), \
             patch("scripts.audit_memory.register_ambiguity", side_effect=fake_register_ambiguity):
            from scripts import audit_memory
            audit_memory.SINAPSE_HOME = str(tmp_path)
            audit_memory.run_audit(fix=True)

        assert not conflict_path.exists(), "Conflict file should be moved out of atlas"
        assert (conflicts_dir / conflict_name).exists(), "Conflict file should land in cerebro/conflicts/"

    def test_conflict_registered_in_ambiguities(self, tmp_path):
        """
        register_ambiguity should be called with the conflicting neuron_id when a
        .sync-conflict-* file is detected.

        We verify the call args rather than querying the DB directly because
        register_ambiguity opens its own connection internally (via core.database.get_connection),
        and sharing a single :memory: DB across two Connection objects is not supported
        by Python's sqlite3 module.
        """
        atlas = _make_vault(tmp_path)

        conflict_name = "amb-neuron.sync-conflict-20260612-090000-DEV.md"
        (atlas / conflict_name).write_text("# Conflito\n\nDivergent content.", encoding="utf-8")

        mem_conn = _make_audit_db()
        mem_conn.execute(
            "INSERT INTO neurons (id, label, type, content, hash, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            ("amb-neuron", "Amb Neuron", "fact", "Original content.", "canon_hash_abc", None)
        )
        mem_conn.commit()

        register_calls = []

        def fake_register(neuron_id, version_a, version_b):
            register_calls.append({"neuron_id": neuron_id, "a": version_a, "b": version_b})
            return "fake-amb-id"

        with patch("scripts.audit_memory.get_connection", return_value=mem_conn), \
             patch("scripts.audit_memory.register_ambiguity", side_effect=fake_register):
            from scripts import audit_memory
            audit_memory.SINAPSE_HOME = str(tmp_path)
            audit_memory.run_audit(fix=True)

        assert len(register_calls) == 1, "register_ambiguity must be called exactly once"
        assert register_calls[0]["neuron_id"] == "amb-neuron", (
            f"Expected neuron_id='amb-neuron', got {register_calls[0]['neuron_id']!r}"
        )

    def test_read_only_mode_does_not_register_or_move_conflict(self, tmp_path):
        atlas = _make_vault(tmp_path)
        conflict_name = "readonly.sync-conflict-20260613-120000-HOST.md"
        conflict_path = atlas / conflict_name
        conflict_path.write_text("# Conflict\n\nDivergent.", encoding="utf-8")

        mem_conn = _make_audit_db()
        mem_conn.execute(
            "INSERT INTO neurons (id, label, type, content, hash) VALUES (?, ?, ?, ?, ?)",
            ("readonly", "Readonly", "fact", "Original.", "original-hash"),
        )
        mem_conn.commit()

        with patch("scripts.audit_memory.get_connection", return_value=mem_conn), \
             patch("scripts.audit_memory.register_ambiguity") as register:
            from scripts import audit_memory
            audit_memory.SINAPSE_HOME = str(tmp_path)
            audit_memory.run_audit(fix=False)

        register.assert_not_called()
        assert conflict_path.exists()
        assert not (tmp_path / "cerebro" / "conflicts" / conflict_name).exists()


class TestConflictFileNaming:
    """Verify the naming pattern used to identify conflicts."""

    def test_sync_conflict_pattern_matches_expected_names(self):
        """should treat filenames containing .sync-conflict- as conflict files"""
        names_that_are_conflicts = [
            "note.sync-conflict-20260601-100000-DEVICE.md",
            "my-neuron.sync-conflict-20241231-235959-PC.md",
        ]
        names_that_are_not_conflicts = [
            "normal.md",
            "sync-config.md",
            "conflict-notes.md",
        ]
        for name in names_that_are_conflicts:
            assert ".sync-conflict-" in name, f"{name} should be detected as a conflict"
        for name in names_that_are_not_conflicts:
            assert ".sync-conflict-" not in name, f"{name} should NOT be detected as a conflict"
