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

import importlib
import re
from pathlib import Path

import pytest
import yaml

from hive_mind.maintenance.windows_jobs import windows_job_specs

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "runtime.yaml"
WINDOWS_JOBS = ROOT / "scripts" / "setup" / "register-windows-jobs.ps1"
RUNTIME_SERVICES = importlib.import_module("hive_mind.maintenance.runtime_services")


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
    """Map unit -> script for each systemd timer in the native owner."""
    blocks = RUNTIME_SERVICES.unit_definitions()
    timers = {k[: -len(".timer")] for k in blocks if k.endswith(".timer")}
    mapping: dict[str, str] = {}
    for unit in timers:
        service = blocks.get(f"{unit}.service", "")
        match = re.search(r"scripts/[\w/]+\.py", service)
        if match:
            mapping[unit] = match.group(0)
    return mapping


def _windows_task_scripts() -> set[str]:
    return {
        job.source_script.replace("\\", "/")
        for job in windows_job_specs(ROOT)
        if job.source_script
    }


def test_legacy_definitions_are_still_readable():
    """Guards the parser itself: if these go empty the parity test is vacuous."""
    assert _systemd_timer_scripts(), "could not parse systemd timers"
    assert _windows_task_scripts(), "could not parse Windows scheduled tasks"


# Legacy scripts whose responsibility now lives in a native command. The
# manifest declares the native command, so a script-path comparison no longer
# finds them — that is the point of porting, not a coverage gap.
PORTED_TO_NATIVE = {
    # D008-R1B: hive-mind backup run --apply
    "scripts/health/backup_databases.py",
}


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
    """No Windows task may point at a script that does not exist.

    D008-R1V found `scripts/maintenance/backup.py` present only as an untracked
    file on the maintainer's machine and duplicated by `backup-databases`, and
    left the task pointing at it — harmless while the untracked file existed,
    but a silent breakage the moment a cutover replaced the working tree.
    P2-R1 closed that: `register-windows-jobs.ps1` now registers HiveMind-Backup
    as the native `hive-mind backup run --apply` command, so no script-path task
    is left dangling. This test fails if one is reintroduced.
    """
    dead = _windows_task_scripts() - _live(_windows_task_scripts())
    assert dead == set(), (
        f"the set of dead legacy tasks changed; re-validate the inventory: {dead}"
    )


def test_backup_task_uses_the_native_command_not_the_retired_wrapper():
    """P2-R1: the scheduled backup must survive a cutover.

    The retired wrapper is not in the repository, so a task still pointing at it
    would start failing the first night after the runtime moved.
    """
    backup = next(job for job in windows_job_specs(ROOT) if job.name == "HiveMind-Backup")

    assert "maintenance\\backup.py" not in (backup.source_script or "")
    assert backup.arguments == "backup run --apply"
    assert backup.execute.endswith(r".venv\Scripts\hive-mind.exe")


def test_manifest_covers_every_systemd_timer():
    missing = (
        set(_systemd_timer_scripts().values()) - _manifest_scripts() - PORTED_TO_NATIVE
    )
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
