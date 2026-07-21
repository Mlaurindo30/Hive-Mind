"""D008 (fatia 4) — shadow scheduler computes next-run, fires nothing (spec F6).

In shadow the scheduler calculates when each job *would* run, from its cron or
interval trigger, and records it. It never fires a job (Anexo D.4). The
SchedulerStore (spec D.6) holds next_run/last_run and the max_instances lease;
MemorySchedulerStore is the in-process default.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hive_mind.daemon.manifest import RuntimeManifest
from hive_mind.daemon.scheduler import (
    MemorySchedulerStore,
    ShadowScheduler,
    next_fire_time,
)


def _manifest(jobs) -> RuntimeManifest:
    return RuntimeManifest.model_validate(
        {"schema_version": 3, "profile": "local-min", "jobs": jobs}
    )


def _job(name, schedule, **extra) -> dict:
    return {"name": name, "command": ["run", name], "schedule": schedule, **extra}


NOW = datetime(2026, 7, 20, 10, 0, 0, tzinfo=timezone.utc)


def test_cron_next_fire_is_computed():
    when = next_fire_time(
        {"type": "cron", "expression": "0 3 * * *", "timezone": "UTC"}, after=NOW
    )
    assert when.hour == 3
    assert when.date() > NOW.date()


def test_interval_next_fire_is_computed():
    when = next_fire_time(
        {"type": "interval", "seconds": 30, "timezone": "UTC"}, after=NOW
    )
    assert (when - NOW).total_seconds() == pytest.approx(30, abs=1)


def test_shadow_scheduler_records_next_run_for_each_job(tmp_path):
    manifest = _manifest(
        [
            _job("dream-cycle", {"type": "cron", "expression": "0 3 * * *",
                                 "timezone": "UTC"}),
            _job("tailer", {"type": "interval", "seconds": 30, "timezone": "UTC"}),
        ]
    )
    scheduler = ShadowScheduler(manifest, store=MemorySchedulerStore(), state_dir=tmp_path)
    plan = scheduler.compute(now=NOW)

    jobs = {j["name"]: j for j in plan["jobs"]}
    assert jobs["dream-cycle"]["next_run"] is not None
    assert jobs["tailer"]["next_run"] is not None
    assert plan["mode"] == "shadow"


def test_shadow_scheduler_writes_only_schedule_state(tmp_path):
    manifest = _manifest(
        [_job("tailer", {"type": "interval", "seconds": 30, "timezone": "UTC"})]
    )
    ShadowScheduler(manifest, store=MemorySchedulerStore(), state_dir=tmp_path).compute(now=NOW)
    files = {p.name for p in tmp_path.iterdir()}
    assert files == {"schedule.shadow.json"}


def test_shadow_scheduler_fires_nothing(tmp_path, monkeypatch):
    import subprocess

    def explode(*a, **k):
        raise AssertionError("shadow scheduler must not fire a job")

    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(subprocess, "run", explode)

    manifest = _manifest(
        [_job("tailer", {"type": "interval", "seconds": 30, "timezone": "UTC"})]
    )
    ShadowScheduler(manifest, store=MemorySchedulerStore(), state_dir=tmp_path).compute(now=NOW)


def test_disabled_job_is_skipped(tmp_path):
    manifest = _manifest(
        [_job("off", {"type": "interval", "seconds": 30, "timezone": "UTC"},
              enabled=False)]
    )
    plan = ShadowScheduler(
        manifest, store=MemorySchedulerStore(), state_dir=tmp_path
    ).compute(now=NOW)
    assert plan["jobs"] == []


class TestSchedulerStore:
    def test_next_run_roundtrips(self):
        store = MemorySchedulerStore()
        assert store.next_run("j") is None
        store.set_next_run("j", NOW)
        assert store.next_run("j") == NOW

    def test_last_run_roundtrips(self):
        store = MemorySchedulerStore()
        store.set_last_run("j", NOW)
        assert store.last_run("j") == NOW

    def test_lease_enforces_max_instances(self):
        store = MemorySchedulerStore()
        assert store.acquire_lease("j", max_instances=1) is True
        # Second concurrent lease is refused.
        assert store.acquire_lease("j", max_instances=1) is False
        store.release_lease("j")
        assert store.acquire_lease("j", max_instances=1) is True

    def test_lease_allows_up_to_max_instances(self):
        store = MemorySchedulerStore()
        assert store.acquire_lease("j", max_instances=2) is True
        assert store.acquire_lease("j", max_instances=2) is True
        assert store.acquire_lease("j", max_instances=2) is False
