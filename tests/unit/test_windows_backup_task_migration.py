"""P2-R1/P4-R1 — Windows scheduled jobs are owned by native CLI logic."""
from __future__ import annotations

from pathlib import Path

from hive_mind.maintenance.windows_jobs import register_windows_jobs, windows_job_specs


ROOT = Path(__file__).resolve().parents[2]

def test_backup_job_targets_the_native_hive_mind_executable():
    backup = next(job for job in windows_job_specs(ROOT) if job.name == "HiveMind-Backup")

    assert backup.execute.endswith(r".venv\Scripts\pythonw.exe")
    assert backup.arguments == "-m hive_mind.cli backup run --apply"
    assert backup.working_directory == str(ROOT)


def test_script_jobs_keep_the_canonical_python_targets():
    jobs = {job.name: job for job in windows_job_specs(ROOT)}

    assert jobs["HiveMind-DreamCycle"].source_script == r"scripts\dream\dream_cycle.py"
    assert jobs["HiveMind-ClaudeMemBridge"].source_script == r"scripts\services\claude_mem_bridge.py"
    assert jobs["HiveMind-KnowledgeHealth"].source_script == r"scripts\health\audit_memory.py"
    assert all(job.schedule_time == "02:00" for job in jobs.values())


def test_native_windows_jobs_dry_run_is_machine_readable():
    report = register_windows_jobs(root=ROOT, apply=False)

    assert report.scanned == 4
    assert report.registered == 0
    assert len(report.entries) == 4
    assert all(entry.status in {"DRY_RUN", "SKIPPED"} for entry in report.entries)


def test_windows_jobs_are_owned_by_native_python():
    source = (ROOT / "src" / "hive_mind" / "maintenance" / "windows_jobs.py").read_text(encoding="utf-8")

    assert "def register_windows_jobs" in source
    assert "Register-ScheduledTask" not in source
    assert "Export-ScheduledTask" not in source
