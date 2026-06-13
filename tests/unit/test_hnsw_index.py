"""
Unit tests for core.hnsw_index — Sprint B4.

These tests do NOT require hnswlib to be installed; the module degrades gracefully
when hnswlib is unavailable. When hnswlib IS available, actual index operations
are patched at the hnswlib.Index level so tests remain fast and hermetic.
"""

import importlib
import sqlite3
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_neurons_db(tmp_path: Path, rows: list[dict]) -> sqlite3.Connection:
    """Create an in-memory (or file-based) SQLite db with a minimal neurons table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE neurons (
            id TEXT PRIMARY KEY,
            content TEXT,
            indexed_at TIMESTAMP
        )
        """
    )
    for row in rows:
        conn.execute(
            "INSERT INTO neurons (id, content, indexed_at) VALUES (?, ?, ?)",
            (row["id"], row.get("content", "hello"), row.get("indexed_at")),
        )
    conn.commit()
    return conn


def _reload_module_without_hnswlib() -> ModuleType:
    """
    Reload core.hnsw_index with hnswlib patched as unavailable.
    Returns the freshly imported module.
    """
    # Remove cached module so reimport triggers the try/except again
    for key in list(sys.modules.keys()):
        if "hnsw_index" in key:
            del sys.modules[key]

    with patch.dict(sys.modules, {"hnswlib": None}):
        mod = importlib.import_module("core.hnsw_index")
    return mod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNoHnswlib:
    """Behaviour when hnswlib is not installed."""

    def test_load_or_create_without_hnswlib(self, tmp_path):
        """load_or_create returns False and raises no exception when hnswlib is missing."""
        mod = _reload_module_without_hnswlib()
        mod._INDEX_PATH = tmp_path / "hnsw_neurons.idx"
        mod._INDEX = None

        result = mod.load_or_create()

        assert result is False

    def test_search_without_hnswlib(self, tmp_path):
        """search returns [] and raises no exception when hnswlib is missing."""
        mod = _reload_module_without_hnswlib()
        mod._INDEX_PATH = tmp_path / "hnsw_neurons.idx"
        mod._INDEX = None

        result = mod.search([0.0] * 384, k=5)

        assert result == []


class TestWithMockedIndex:
    """Behaviour when hnswlib IS available (operations patched for hermeticity)."""

    @pytest.fixture(autouse=True)
    def _reset_module_state(self, tmp_path):
        """Ensure module-level state is clean before each test."""
        import core.hnsw_index as mod
        mod._INDEX_PATH = tmp_path / "hnsw_neurons.idx"
        mod._INDEX = None
        mod._id_to_label = {}
        mod._label_to_id = {}
        mod._next_label = 0
        yield
        # Cleanup
        mod._INDEX = None
        mod._id_to_label = {}
        mod._label_to_id = {}
        mod._next_label = 0

    def test_add_neuron_updates_indexed_at(self, tmp_path):
        """add_neuron sets indexed_at in the DB when conn is provided."""
        import core.hnsw_index as mod

        if mod._hnswlib is None:
            pytest.skip("hnswlib not installed")

        # Build a real-ish mock index
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 0
        mock_index.get_max_elements.return_value = 10_000
        mod._INDEX = mock_index

        conn = _make_neurons_db(tmp_path, [{"id": "n1", "content": "test"}])

        result = mod.add_neuron("n1", [0.1] * 384, conn=conn)

        assert result is True
        row = conn.execute("SELECT indexed_at FROM neurons WHERE id='n1'").fetchone()
        assert row["indexed_at"] is not None

    def test_incremental_update_skips_already_indexed(self, tmp_path):
        """incremental_update only processes neurons with indexed_at IS NULL."""
        import core.hnsw_index as mod

        if mod._hnswlib is None:
            pytest.skip("hnswlib not installed")

        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 0
        mock_index.get_max_elements.return_value = 10_000
        mod._INDEX = mock_index

        conn = _make_neurons_db(
            tmp_path,
            [
                {"id": "already", "content": "old", "indexed_at": "2026-01-01 00:00:00"},
                {"id": "pending", "content": "new", "indexed_at": None},
            ],
        )

        embed_fn = MagicMock(return_value=[0.1] * 384)

        # Patch _save_index to avoid touching disk
        with patch.object(mod, "_save_index"):
            count = mod.incremental_update(conn, embed_fn)

        assert count == 1
        embed_fn.assert_called_once()
        # The only call should be for "pending"
        assert embed_fn.call_args[0][0] == "new"

    def test_rebuild_counts_neurons(self, tmp_path):
        """rebuild_from_db returns the number of neurons successfully embedded."""
        import core.hnsw_index as mod

        if mod._hnswlib is None:
            pytest.skip("hnswlib not installed")

        conn = _make_neurons_db(
            tmp_path,
            [
                {"id": "a", "content": "alpha"},
                {"id": "b", "content": "beta"},
                {"id": "c", "content": "gamma"},
            ],
        )

        embed_fn = MagicMock(return_value=[0.1] * 384)

        # Patch the hnswlib.Index constructor inside the module so no real index is built
        mock_index = MagicMock()
        mock_index.get_current_count.return_value = 0
        mock_index.get_max_elements.return_value = 10_000

        with patch.object(mod._hnswlib, "Index", return_value=mock_index):
            with patch.object(mod, "_save_index"):
                count = mod.rebuild_from_db(conn, embed_fn)

        assert count == 3
        assert embed_fn.call_count == 3

    def test_saved_map_is_loaded_with_index(self, tmp_path):
        import core.hnsw_index as mod

        if mod._hnswlib is None:
            pytest.skip("hnswlib not installed")

        conn = _make_neurons_db(tmp_path, [{"id": "persisted", "content": "alpha"}])
        assert mod.rebuild_from_db(conn, lambda _: [0.1] * 384) == 1

        mod._INDEX = None
        mod._id_to_label = {}
        mod._label_to_id = {}
        mod._next_label = 0
        assert mod.load_or_create()
        assert mod.search([0.1] * 384, k=1)[0]["neuron_id"] == "persisted"

    def test_upsert_vectors_persists_indexed_at(self):
        import core.hnsw_index as mod

        if mod._hnswlib is None:
            pytest.skip("hnswlib not installed")
        conn = _make_neurons_db(Path("."), [{"id": "n1", "content": "alpha"}])
        assert mod.upsert_vectors(conn, {"n1": [0.2] * 384}) == 1
        assert conn.execute(
            "SELECT indexed_at FROM neurons WHERE id='n1'"
        ).fetchone()["indexed_at"]

    def test_rebuild_from_vectors_preserves_id_mapping(self):
        import core.hnsw_index as mod

        if mod._hnswlib is None:
            pytest.skip("hnswlib not installed")
        conn = _make_neurons_db(
            Path("."),
            [{"id": "first", "content": "same"}, {"id": "second", "content": "same"}],
        )
        count = mod.rebuild_from_vectors(
            conn,
            {"second": [0.0] * 383 + [1.0], "first": [1.0] + [0.0] * 383},
        )
        assert count == 2
        assert mod.search([1.0] + [0.0] * 383, k=1)[0]["neuron_id"] == "first"
