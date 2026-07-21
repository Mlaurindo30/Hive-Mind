"""D008 (fatia 5) — SqliteSchedulerStore: scheduler persistence (spec D.6).

Same SchedulerStore interface as MemorySchedulerStore, backed by SQLite in
state_dir/jobs.db, so next_run/last_run and leases survive a restart. The
in-memory store was documented as not surviving a restart; this is its
production replacement.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hive_mind.daemon.scheduler import SqliteSchedulerStore

NOW = datetime(2026, 7, 20, 3, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 7, 21, 3, 0, 0, tzinfo=timezone.utc)


def test_next_run_roundtrips(tmp_path):
    store = SqliteSchedulerStore(tmp_path)
    assert store.next_run("dream-cycle") is None
    store.set_next_run("dream-cycle", NOW)
    assert store.next_run("dream-cycle") == NOW


def test_last_run_roundtrips(tmp_path):
    store = SqliteSchedulerStore(tmp_path)
    store.set_last_run("dream-cycle", NOW)
    assert store.last_run("dream-cycle") == NOW


def test_values_survive_a_new_store_instance(tmp_path):
    """The whole point: persistence across a restart."""
    first = SqliteSchedulerStore(tmp_path)
    first.set_next_run("tailer", NOW)
    first.set_last_run("tailer", LATER)
    del first

    second = SqliteSchedulerStore(tmp_path)
    assert second.next_run("tailer") == NOW
    assert second.last_run("tailer") == LATER


def test_set_next_run_is_upsert(tmp_path):
    store = SqliteSchedulerStore(tmp_path)
    store.set_next_run("j", NOW)
    store.set_next_run("j", LATER)
    assert store.next_run("j") == LATER


def test_lease_enforces_max_instances(tmp_path):
    store = SqliteSchedulerStore(tmp_path)
    assert store.acquire_lease("j", max_instances=1) is True
    assert store.acquire_lease("j", max_instances=1) is False
    store.release_lease("j")
    assert store.acquire_lease("j", max_instances=1) is True


def test_lease_allows_up_to_max_instances(tmp_path):
    store = SqliteSchedulerStore(tmp_path)
    assert store.acquire_lease("j", max_instances=2) is True
    assert store.acquire_lease("j", max_instances=2) is True
    assert store.acquire_lease("j", max_instances=2) is False


def test_release_below_zero_is_safe(tmp_path):
    store = SqliteSchedulerStore(tmp_path)
    store.release_lease("never-acquired")  # must not raise or go negative
    assert store.acquire_lease("never-acquired", max_instances=1) is True


def test_creates_jobs_db_in_state_dir(tmp_path):
    store = SqliteSchedulerStore(tmp_path)
    store.set_next_run("j", NOW)
    assert (tmp_path / "jobs.db").exists()


def test_timezone_is_preserved(tmp_path):
    from zoneinfo import ZoneInfo

    sp = datetime(2026, 7, 20, 3, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    store = SqliteSchedulerStore(tmp_path)
    store.set_next_run("j", sp)
    got = store.next_run("j")
    assert got == sp
    assert got.utcoffset() == sp.utcoffset()
