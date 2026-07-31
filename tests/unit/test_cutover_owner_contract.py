"""P2-R4 — the candidate's persisted runtime surfaces must be cutover-clean.

The live path audit finds one violation today (capture-realtime running from the
staging worktree); that is cleared by the P4 cutover, not by editing the
repository. What *can* be pinned now is that nothing the candidate ships — the
runtime manifest, the Windows job definitions, the supervisor launcher — points
at a forbidden family. If a future change reintroduced `Hive-Mind-Consolidation`,
a canonical `.tmp`/`backups` target, or a stray worktree into those files, this
suite fails before it can reach a machine.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hive_mind.maintenance.windows_jobs import windows_job_specs
from hive_mind.validation.runtime_paths import (
    RuntimePathReference,
    find_runtime_path_violations,
)


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = r"D:\Hive-Mind"
CONTRACT = ROOT / "docs" / "operations" / "cutover-owner-contract.md"


def _manifest_command_references() -> list[RuntimePathReference]:
    manifest = yaml.safe_load((ROOT / "config" / "runtime.yaml").read_text(encoding="utf-8"))
    refs = []
    for job in manifest.get("jobs", []):
        command = " ".join(job.get("command", []))
        refs.append(RuntimePathReference(source=f"runtime.yaml:{job['name']}", value=command))
    for service in manifest.get("services", []):
        command = " ".join(service.get("command", []))
        refs.append(RuntimePathReference(source=f"runtime.yaml:{service.get('name')}", value=command))
    return refs


def test_runtime_manifest_has_no_forbidden_targets():
    findings = find_runtime_path_violations(_manifest_command_references(), CANONICAL)

    assert findings == [], [f.to_dict() for f in findings]


def test_windows_job_definitions_have_no_forbidden_targets():
    spec_refs = [
        RuntimePathReference(
            source=f"windows_job:{job.name}",
            value=" ".join(
                part for part in (job.execute, job.arguments, job.working_directory, job.source_script or "")
                if part
            ),
        )
        for job in windows_job_specs(ROOT)
    ]
    findings = find_runtime_path_violations(spec_refs, CANONICAL)

    assert findings == [], [f.to_dict() for f in findings]


def test_supervisor_runtime_has_no_forbidden_targets():
    source = (ROOT / "src" / "hive_mind" / "maintenance" / "windows_runtime.py").read_text(encoding="utf-8")
    ref = RuntimePathReference(source="windows_runtime.py", value=source)
    assert find_runtime_path_violations([ref], str(ROOT)) == []


def test_backup_job_owner_is_the_native_command():
    """The one owner P2-R1 actually rewrote, checked end to end here."""
    backup = next(job for job in windows_job_specs(ROOT) if job.name == "HiveMind-Backup")

    assert backup.execute.endswith(r".venv\Scripts\hive-mind.exe")
    assert backup.arguments == "backup run --apply"


def test_contract_document_exists_and_names_the_one_live_violation():
    text = CONTRACT.read_text(encoding="utf-8")

    assert "capture-realtime" in text
    assert "Hive-Mind-Consolidation" in text
    # It must be explicit that the two failing tasks are not staging code bugs.
    assert "not code defects" in text or "not a code defect" in text


def test_policy_flags_a_staging_capture_owner():
    """Sanity check that the widened policy still catches the real case."""
    ref = RuntimePathReference(
        source="process:capture:command_line",
        value=r'"D:\Hive-Mind\.venv\Scripts\python.exe" '
        r"D:\Hive-Mind-Consolidation\20260722-201726\repo\scripts\capture\capture-realtime.py",
    )

    findings = find_runtime_path_violations([ref], CANONICAL)

    assert len(findings) == 1
    assert findings[0].matched == "hive-mind-consolidation"
