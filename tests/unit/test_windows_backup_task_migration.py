"""P2-R1 — HiveMind-Backup must survive the native cutover.

Today the live task runs `scripts\\maintenance\\backup.py`, a file that exists
only as an untracked artefact on the maintainer's machine. D008-R1V retired it
in favour of `hive-mind backup run --apply`, which `config/runtime.yaml`
schedules as `backup-databases`. A cutover that replaced the working tree would
therefore leave the 02:00 job pointing at a target that no longer exists, and it
would fail silently the first night.

These tests pin the migration contract in `register-windows-jobs.ps1`. The
PowerShell-backed ones run against a **temporary task name** and are skipped
when Task Scheduler is unavailable or refuses registration; the live
`HiveMind-Backup` task is never read for mutation, never modified and never
deleted.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
WINDOWS_JOBS = ROOT / "scripts" / "setup" / "register-windows-jobs.ps1"
TEST_TASK = "HiveMindTest-P2R1-BackupMigration"

pytestmark = pytest.mark.skipif(
    shutil.which("powershell") is None, reason="Windows PowerShell not available"
)


def _powershell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", script],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Contract of the installer script itself (no Task Scheduler involved)
# ---------------------------------------------------------------------------


def test_backup_job_targets_the_canonical_venv_executable():
    text = WINDOWS_JOBS.read_text(encoding="utf-8-sig")

    assert "$hiveMind=Join-Path $Root '.venv\\Scripts\\hive-mind.exe'" in text
    assert "Execute=$hiveMind" in text
    assert "Arguments='backup run --apply'" in text


def test_backup_job_keeps_the_0200_schedule_and_working_directory():
    text = WINDOWS_JOBS.read_text(encoding="utf-8-sig")

    assert "-Daily -At '02:00'" in text
    assert "-WorkingDirectory $Root" in text


def test_installer_exports_the_previous_definition_before_replacing_it():
    text = WINDOWS_JOBS.read_text(encoding="utf-8-sig")

    assert "function Export-HiveMindTaskDefinition" in text
    assert "function Restore-HiveMindTaskDefinition" in text
    assert "Export-ScheduledTask" in text
    # The export must happen before the task is rewritten.
    assert text.index("Export-HiveMindTaskDefinition -TaskName $job.Name") < text.index(
        "Register-ScheduledTask -TaskName $job.Name -Action $action"
    )


def test_installer_refuses_to_register_a_missing_executable():
    """Trading a broken target for another broken target is not a migration."""
    text = WINDOWS_JOBS.read_text(encoding="utf-8-sig")

    assert "if(-not(Test-Path -LiteralPath $job.Execute))" in text
    assert "leaving the existing task untouched" in text


def test_no_reference_to_the_retired_wrapper_remains():
    text = WINDOWS_JOBS.read_text(encoding="utf-8-sig")

    assert "maintenance\\backup.py" not in text
    assert "maintenance/backup.py" not in text


# ---------------------------------------------------------------------------
# Behaviour against a disposable task — never HiveMind-Backup
# ---------------------------------------------------------------------------


@pytest.fixture
def disposable_task():
    """Register a throwaway task, yield its name, always unregister it."""
    created = _powershell(
        f"""
$ErrorActionPreference='Stop'
$action=New-ScheduledTaskAction -Execute 'C:\\Windows\\System32\\cmd.exe' `
    -Argument '/c echo legacy' -WorkingDirectory 'C:\\Windows\\Temp'
$trigger=New-ScheduledTaskTrigger -Daily -At '02:00'
Register-ScheduledTask -TaskName '{TEST_TASK}' -Action $action -Trigger $trigger -Force | Out-Null
"""
    )
    if created.returncode != 0:
        pytest.skip(f"cannot register a test task here: {created.stderr.strip()[:200]}")
    try:
        yield TEST_TASK
    finally:
        _powershell(
            f"Unregister-ScheduledTask -TaskName '{TEST_TASK}' -Confirm:$false "
            f"-ErrorAction SilentlyContinue"
        )


def test_the_live_backup_task_is_never_touched_by_this_suite():
    """Guard: the disposable name must not collide with the real one."""
    assert TEST_TASK != "HiveMind-Backup"
    assert TEST_TASK.startswith("HiveMindTest-")


def test_export_then_restore_round_trips_the_definition(disposable_task, tmp_path):
    result = _powershell(
        f"""
$ErrorActionPreference='Stop'
. '{WINDOWS_JOBS}' -WhatIfOnly -Root '{ROOT}' | Out-Null
$backup = Export-HiveMindTaskDefinition -TaskName '{disposable_task}' -Destination '{tmp_path}'
if (-not $backup) {{ throw 'no backup produced' }}
Write-Output "BACKUP=$backup"

# Migrate it the way the installer does.
$action=New-ScheduledTaskAction -Execute 'C:\\Windows\\System32\\cmd.exe' `
    -Argument '/c echo migrated' -WorkingDirectory 'C:\\Windows'
$trigger=New-ScheduledTaskTrigger -Daily -At '02:00'
Register-ScheduledTask -TaskName '{disposable_task}' -Action $action -Trigger $trigger -Force | Out-Null
$after=(Get-ScheduledTask -TaskName '{disposable_task}').Actions[0].Arguments
Write-Output "MIGRATED=$after"

# Roll back from the exported XML.
Restore-HiveMindTaskDefinition -TaskName '{disposable_task}' -Path $backup
$rolled=(Get-ScheduledTask -TaskName '{disposable_task}').Actions[0].Arguments
Write-Output "ROLLEDBACK=$rolled"
"""
    )

    assert result.returncode == 0, result.stderr
    assert "MIGRATED=/c echo migrated" in result.stdout
    assert "ROLLEDBACK=/c echo legacy" in result.stdout, (
        "rollback did not restore the original command line"
    )


def test_export_returns_nothing_for_an_unknown_task(tmp_path):
    result = _powershell(
        f"""
$ErrorActionPreference='Stop'
. '{WINDOWS_JOBS}' -WhatIfOnly -Root '{ROOT}' | Out-Null
$backup = Export-HiveMindTaskDefinition -TaskName 'HiveMindTest-DoesNotExist-P2R1' `
    -Destination '{tmp_path}'
if ($backup) {{ throw "unexpected backup: $backup" }}
Write-Output 'NOBACKUP'
"""
    )

    assert result.returncode == 0, result.stderr
    assert "NOBACKUP" in result.stdout


def test_whatif_lists_jobs_without_registering_anything():
    result = _powershell(f". '{WINDOWS_JOBS}' -WhatIfOnly -Root '{ROOT}'")

    assert result.returncode == 0, result.stderr
    assert "HiveMind-Backup" in result.stdout
    assert "HiveMind-DreamCycle" in result.stdout
