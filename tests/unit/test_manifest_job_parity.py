"""D008-R1 — the manifest must cover every scheduled job (audit finding A-05/A-06).

`config/runtime.yaml` is declared the single source of truth for jobs, but the
legacy owners still hold their own lists:

  - `scripts/setup/install_services.py` — the Linux systemd timers, which are
    the proven reference implementation;
  - `scripts/setup/register-windows-jobs.ps1` — the Windows Task Scheduler list.

If the manifest does not cover a job those owners run, a cutover would stop it
silently. This suite reads the legacy definitions and asserts parity, so the
manifest cannot drift out of completeness unnoticed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "runtime.yaml"
INSTALL_SERVICES = ROOT / "scripts" / "setup" / "install_services.py"
WINDOWS_JOBS = ROOT / "scripts" / "setup" / "register-windows-jobs.ps1"


def _manifest_jobs() -> dict[str, dict]:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    return {job["name"]: job for job in data.get("jobs", [])}


def _manifest_scripts() -> set[str]:
    """Every script path the manifest schedules, normalised to posix."""
    scripts = set()
    for job in _manifest_jobs().values():
        for part in job.get("command", []):
            if part.endswith(".py"):
                scripts.add(part.replace("\\", "/").lstrip("./"))
    return scripts


def _systemd_timer_scripts() -> dict[str, str]:
    """Map unit -> script for each systemd timer in the legacy installer."""
    source = INSTALL_SERVICES.read_text(encoding="utf-8")
    blocks = dict(
        re.findall(
            r'"(sinapse-[a-z-]+\.(?:timer|service))":\s*f?"""(.*?)"""', source, re.S
        )
    )
    timers = {k[: -len(".timer")] for k in blocks if k.endswith(".timer")}
    mapping: dict[str, str] = {}
    for unit in timers:
        service = blocks.get(f"{unit}.service", "")
        match = re.search(r"scripts/[\w/]+\.py", service)
        if match:
            mapping[unit] = match.group(0)
    return mapping


def _windows_task_scripts() -> set[str]:
    text = WINDOWS_JOBS.read_text(encoding="utf-8-sig")
    return {
        m.replace("\\", "/")
        for m in re.findall(r"Script='([^']+)'", text)
    }


def test_legacy_definitions_are_still_readable():
    """Guards the parser itself: if these go empty the parity test is vacuous."""
    assert _systemd_timer_scripts(), "could not parse systemd timers"
    assert _windows_task_scripts(), "could not parse Windows scheduled tasks"


def _live(scripts: set[str]) -> set[str]:
    """Only legacy entries whose script actually exists count for parity.

    register-windows-jobs.ps1 guards every task with `Test-Path ... continue`,
    so a task pointing at a missing script is never registered. Requiring the
    manifest to carry it would mean porting a dead job by inertia.
    """
    return {s for s in scripts if (ROOT / s).is_file()}


def test_manifest_covers_every_live_windows_scheduled_task():
    missing = _live(_windows_task_scripts()) - _manifest_scripts()
    assert missing == set(), (
        "config/runtime.yaml does not schedule jobs the Windows Task Scheduler "
        f"still runs; a cutover would stop them silently: {sorted(missing)}"
    )


def test_dead_windows_tasks_are_deliberately_excluded():
    """Documents the jobs intentionally NOT carried over, with the reason.

    D008-R1V found `scripts/maintenance/backup.py` present only as an untracked
    file on the maintainer's machine and duplicated by `backup-databases`. It is
    excluded on purpose; this test fails if it ever becomes real code, forcing a
    fresh decision instead of a silent gap.
    """
    dead = _windows_task_scripts() - _live(_windows_task_scripts())
    assert dead == {"scripts/maintenance/backup.py"}, (
        f"the set of dead legacy tasks changed; re-validate the inventory: {dead}"
    )


def test_manifest_covers_every_systemd_timer():
    missing = set(_systemd_timer_scripts().values()) - _manifest_scripts()
    assert missing == set(), (
        "config/runtime.yaml does not schedule jobs the Linux systemd timers "
        f"still run: {sorted(missing)}"
    )


def test_dream_cycle_keeps_the_canonical_linux_schedule():
    """The Linux reference runs the bridge at 02:45 and the dream at 03:00.

    The Windows Task Scheduler ran the dream at 02:00, losing that ordering.
    The manifest must keep the proven schedule.
    """
    dream = _manifest_jobs()["dream-cycle"]
    assert dream["schedule"]["expression"] == "0 3 * * *"


def test_bridge_runs_before_the_dream_cycle():
    """The bridge feeds the dream; ordering is behaviour, not cosmetics."""
    jobs = _manifest_jobs()
    bridge = next(
        (j for n, j in jobs.items() if "bridge" in n), None
    )
    assert bridge is not None, "claude-mem bridge job missing from the manifest"

    def minutes(expr: str) -> int:
        minute, hour = expr.split()[0], expr.split()[1]
        return int(hour) * 60 + int(minute)

    assert minutes(bridge["schedule"]["expression"]) < minutes(
        jobs["dream-cycle"]["schedule"]["expression"]
    ), "the bridge must run before the dream cycle"
