from __future__ import annotations

import importlib.util
import os
import sqlite3
import threading
import time
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


def test_embedding_does_not_hold_a_write_lock_on_claude_mem(
        tmp_path, monkeypatch):
    sqlite_vec = pytest.importorskip("sqlite_vec")
    worker = _load_worker()
    path = tmp_path / "claude-mem.db"
    entered_embed = threading.Event()
    release_embed = threading.Event()

    def slow_embed(_text):
        entered_embed.set()
        assert release_embed.wait(5)
        return [0.1] * worker.DIMENSIONS

    monkeypatch.setattr(worker, "embed", slow_embed)
    sync_conn = sqlite3.connect(path, timeout=0.1, check_same_thread=False)
    sync_conn.enable_load_extension(True)
    sqlite_vec.load(sync_conn)
    sync_conn.enable_load_extension(False)
    sync_conn.execute(
        "CREATE TABLE observations ("
        "id INTEGER PRIMARY KEY, narrative TEXT, text TEXT, facts TEXT)"
    )
    worker._ensure_schema(sync_conn)
    sync_conn.execute(
        "INSERT INTO observations VALUES (1, 'pending vector', NULL, NULL)"
    )
    sync_conn.commit()

    thread = threading.Thread(target=worker.sync_vectors, args=(sync_conn,))
    thread.start()
    assert entered_embed.wait(2)
    try:
        with sqlite3.connect(path, timeout=0.1) as writer:
            writer.execute(
                "INSERT INTO observations VALUES"
                " (2, 'claude mem live write', NULL, NULL)"
            )
    finally:
        release_embed.set()
        thread.join(5)

    assert not thread.is_alive()


def test_vector_sync_retries_a_brief_external_write_lock(tmp_path, monkeypatch):
    sqlite_vec = pytest.importorskip("sqlite_vec")
    worker = _load_worker()
    monkeypatch.setattr(worker, "embed", lambda _text: [0.1] * worker.DIMENSIONS)
    path = tmp_path / "claude-mem.db"
    sync_conn = sqlite3.connect(path, timeout=0.01, check_same_thread=False)
    sync_conn.execute("PRAGMA busy_timeout=1")
    sync_conn.enable_load_extension(True)
    sqlite_vec.load(sync_conn)
    sync_conn.enable_load_extension(False)
    sync_conn.execute(
        "CREATE TABLE observations ("
        "id INTEGER PRIMARY KEY, narrative TEXT, text TEXT, facts TEXT)"
    )
    worker._ensure_schema(sync_conn)
    sync_conn.execute("INSERT INTO observations VALUES (1, 'pending', NULL, NULL)")
    sync_conn.commit()

    blocker = sqlite3.connect(path, timeout=0.01, check_same_thread=False)
    blocker.execute("BEGIN IMMEDIATE")
    outcome: list[int] = []
    thread = threading.Thread(target=lambda: outcome.append(worker.sync_vectors(sync_conn)))
    thread.start()
    time.sleep(0.1)
    blocker.commit()
    thread.join(5)

    assert not thread.is_alive()
    assert outcome == [1]


def test_startup_sync_runs_in_the_background(tmp_path, monkeypatch):
    worker = _load_worker()
    conn = sqlite3.connect(tmp_path / "worker.db", check_same_thread=False)
    entered = threading.Event()
    release = threading.Event()

    def slow_sync(_conn, *, limit):
        assert limit == worker.STARTUP_SYNC_LIMIT
        entered.set()
        assert release.wait(2)
        return 0

    monkeypatch.setattr(worker, "sync_vectors", slow_sync)
    monkeypatch.setattr(worker, "_vector_count", lambda _conn: 0)
    thread = worker.start_startup_sync(conn)
    assert entered.wait(1)
    assert thread.is_alive()
    release.set()
    thread.join(2)
    assert not thread.is_alive()


def test_http_server_is_actually_threaded():
    worker = _load_worker()
    assert issubclass(worker.ThreadedHTTPServer, worker.ThreadingHTTPServer)
