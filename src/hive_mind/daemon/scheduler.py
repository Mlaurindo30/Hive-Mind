"""Job scheduler (spec F6 shadow / D.6 store).

In shadow ownership the scheduler only *computes* when each job would next
run, from its cron or interval trigger, and records it. It fires nothing
(Anexo D.4). Firing jobs is a managed operation (F7).

`next_fire_time` uses APScheduler's trigger classes (spec D.6 sanctions
APScheduler; no home-grown cron parser). The `SchedulerStore` interface holds
next_run/last_run and the `max_instances` lease; `MemorySchedulerStore` is the
in-process default (does not survive a restart — the SQLite-backed store is
F7).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from hive_mind.daemon.manifest import RuntimeManifest

SCHEDULE_STATE_FILENAME = "schedule.shadow.json"


def _timezone(name: Optional[str]):
    from zoneinfo import ZoneInfo

    return ZoneInfo(name) if name else ZoneInfo("UTC")


def next_fire_time(schedule: dict, *, after: datetime) -> datetime:
    """Compute the next fire time for a cron or interval schedule.

    `after` must be timezone-aware; the returned time is in the job's timezone.
    """
    from datetime import timedelta

    tz = _timezone(schedule.get("timezone"))
    reference = after.astimezone(tz)
    kind = schedule["type"]
    if kind == "cron":
        from apscheduler.triggers.cron import CronTrigger

        trigger = CronTrigger.from_crontab(schedule["expression"], timezone=tz)
        return trigger.get_next_fire_time(None, reference)
    if kind == "interval":
        # An interval's next run after `after` is unambiguous; compute it
        # directly rather than anchoring APScheduler's IntervalTrigger to its
        # own wall-clock start_time.
        return reference + timedelta(seconds=int(schedule["seconds"]))
    raise ValueError(f"unknown schedule type: {kind}")  # pragma: no cover


class SchedulerStore:
    """Interface for scheduler persistence (spec D.6)."""

    def next_run(self, job: str) -> Optional[datetime]:  # pragma: no cover
        raise NotImplementedError

    def set_next_run(self, job: str, when: datetime) -> None:  # pragma: no cover
        raise NotImplementedError

    def last_run(self, job: str) -> Optional[datetime]:  # pragma: no cover
        raise NotImplementedError

    def set_last_run(self, job: str, when: datetime) -> None:  # pragma: no cover
        raise NotImplementedError

    def acquire_lease(self, job: str, max_instances: int) -> bool:  # pragma: no cover
        raise NotImplementedError

    def release_lease(self, job: str) -> None:  # pragma: no cover
        raise NotImplementedError


class MemorySchedulerStore(SchedulerStore):
    """In-process store. Does not survive a restart (SQLite store is F7)."""

    def __init__(self) -> None:
        self._next: dict[str, datetime] = {}
        self._last: dict[str, datetime] = {}
        self._leases: dict[str, int] = {}

    def next_run(self, job: str) -> Optional[datetime]:
        return self._next.get(job)

    def set_next_run(self, job: str, when: datetime) -> None:
        self._next[job] = when

    def last_run(self, job: str) -> Optional[datetime]:
        return self._last.get(job)

    def set_last_run(self, job: str, when: datetime) -> None:
        self._last[job] = when

    def acquire_lease(self, job: str, max_instances: int) -> bool:
        active = self._leases.get(job, 0)
        if active >= max_instances:
            return False
        self._leases[job] = active + 1
        return True

    def release_lease(self, job: str) -> None:
        active = self._leases.get(job, 0)
        if active > 0:
            self._leases[job] = active - 1


class ShadowScheduler:
    """Computes job schedules passively; fires nothing (spec F6)."""

    def __init__(
        self,
        manifest: RuntimeManifest,
        store: SchedulerStore,
        state_dir: Path | str,
    ) -> None:
        self.manifest = manifest
        self.store = store
        self.state_dir = Path(state_dir)

    def compute(self, now: datetime) -> dict:
        jobs = []
        for job in self.manifest.jobs:
            if not job.enabled:
                continue
            schedule = job.schedule.model_dump()
            when = next_fire_time(schedule, after=now)
            self.store.set_next_run(job.name, when)
            jobs.append(
                {
                    "name": job.name,
                    "type": job.schedule.type,
                    "next_run": when.isoformat(),
                    "last_run": (
                        self.store.last_run(job.name).isoformat()
                        if self.store.last_run(job.name)
                        else None
                    ),
                    "max_instances": job.schedule.max_instances,
                    "would_fire": True,
                }
            )
        plan = {"mode": "shadow", "job_count": len(jobs), "jobs": jobs}
        self._persist(plan)
        return plan

    def _persist(self, plan: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        target = self.state_dir / SCHEDULE_STATE_FILENAME
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
