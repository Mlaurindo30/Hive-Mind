from __future__ import annotations

import importlib.util
import os
import sqlite3
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load_worker():
    os.environ.setdefault("CLAUDE_MEM_DB", ":memory:")
    spec = importlib.util.spec_from_file_location(
        "sqlite_vec_worker",
        ROOT / "plugins" / "sqlite-vec-worker" / "worker.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sqlite_vec_worker_syncs_incremental_observations(monkeypatch):
    sqlite_vec = pytest.importorskip("sqlite_vec")
    worker = _load_worker()
    monkeypatch.setattr(worker, "embed", lambda text: [0.1] * worker.DIMENSIONS)

    conn = sqlite3.connect(":memory:")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute(
        """
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
            narrative TEXT,
            text TEXT,
            facts TEXT
        )
        """
    )
    worker._ensure_schema(conn)
    conn.execute(
        "INSERT INTO observations(id, narrative, text, facts) VALUES (1, 'old observation', NULL, NULL)"
    )
    conn.execute(
        "INSERT INTO observations(id, narrative, text, facts) VALUES (2, 'new observation', NULL, NULL)"
    )
    conn.execute(
        "INSERT INTO vec_observations(rowid, embedding) VALUES (1, ?)",
        (str([0.2] * worker.DIMENSIONS),),
    )

    assert worker.sync_vectors(conn) == 1
    assert conn.execute("SELECT COUNT(*) FROM vec_observations").fetchone()[0] == 2

    conn.execute("DELETE FROM observations WHERE id = 1")
    worker.sync_vectors(conn)
    assert conn.execute("SELECT COUNT(*) FROM vec_observations WHERE rowid = 1").fetchone()[0] == 0
