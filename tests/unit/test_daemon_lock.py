"""D007 — single-instance lock (spec Anexo D.2).

Exactly one `hive-mindd` per host. A second acquisition fails with a clear,
typed error and never corrupts the first holder's ownership.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

import hive_mind.daemon.lock as lock_mod
from hive_mind.daemon.lock import (
    SingleInstanceLock,
    SingleInstanceLockError,
)


@pytest.fixture(autouse=True)
def _isolate_windows_mutex(monkeypatch):
    """Windows: o lock de produção usa um named mutex host-wide.

    Num host com um hive-mindd real rodando, o teste colidiria com o mutex
    global. Cada teste ganha um kernel object name próprio, preservando o
    comportamento testado sem depender de não haver daemon ativo.
    """
    if sys.platform == "win32":
        monkeypatch.setattr(
            lock_mod, "_MUTEX_NAME", f"Local\\Hive-Mind-test-{uuid.uuid4().hex}"
        )


def test_acquire_then_release_is_reusable(tmp_path):
    lock = SingleInstanceLock(state_dir=tmp_path)
    lock.acquire()
    assert lock.held is True
    lock.release()
    assert lock.held is False
    # Re-acquiring after release must work.
    lock.acquire()
    assert lock.held is True
    lock.release()


def test_second_instance_is_rejected_with_clear_error(tmp_path):
    first = SingleInstanceLock(state_dir=tmp_path)
    first.acquire()
    try:
        second = SingleInstanceLock(state_dir=tmp_path)
        with pytest.raises(SingleInstanceLockError) as excinfo:
            second.acquire()
        message = str(excinfo.value).lower()
        assert "already" in message or "instance" in message
    finally:
        first.release()


def test_release_after_second_instance_frees_the_slot(tmp_path):
    first = SingleInstanceLock(state_dir=tmp_path)
    first.acquire()
    first.release()
    # Now a fresh instance can take it.
    second = SingleInstanceLock(state_dir=tmp_path)
    second.acquire()
    assert second.held is True
    second.release()


def test_context_manager_releases_on_exit(tmp_path):
    with SingleInstanceLock(state_dir=tmp_path) as lock:
        assert lock.held is True
    assert lock.held is False
    # Slot is free again.
    other = SingleInstanceLock(state_dir=tmp_path)
    other.acquire()
    other.release()


def test_double_release_is_idempotent(tmp_path):
    lock = SingleInstanceLock(state_dir=tmp_path)
    lock.acquire()
    lock.release()
    lock.release()  # must not raise
    assert lock.held is False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock path")
def test_posix_uses_a_lock_file_in_state_dir(tmp_path):
    lock = SingleInstanceLock(state_dir=tmp_path)
    lock.acquire()
    try:
        assert (tmp_path / "daemon.lock").exists()
    finally:
        lock.release()


def test_state_dir_is_created_if_missing(tmp_path):
    nested = tmp_path / "does" / "not" / "exist"
    lock = SingleInstanceLock(state_dir=nested)
    lock.acquire()
    try:
        assert nested.is_dir()
    finally:
        lock.release()
