#!/usr/bin/env python3
"""Compatibility entry point for packaged Windows post-reboot validation."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for import_path in (ROOT, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from hive_mind.validation.post_reboot_windows import validate_live_runtime

try:
    from scripts.health.audit_runtime_paths_windows import audit_runtime_paths
except ModuleNotFoundError:
    from audit_runtime_paths_windows import audit_runtime_paths

REPORT = ROOT / "logs" / "post-reboot-validation.json"
_BOOT_CONVERGENCE_SECONDS = 90
_BOOT_POLL_SECONDS = 3


def task_exists(name: str) -> bool:
    """Compatibility Scheduler observation, hidden if a fallback is needed."""

    return subprocess.run(
        ["schtasks", "/Query", "/TN", name],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).returncode == 0


def _transient_boot_failure(failures: tuple[str, ...]) -> bool:
    """Return whether a report can become healthy while logon is settling."""
    return bool(failures) and all(
        failure == "stale_managed_state"
        or failure == "dead_supervisor"
        or failure.startswith("dead_child:")
        or failure.startswith("missing_child_pid:")
        or failure.startswith("unhealthy_required_service:")
        for failure in failures
    )


def _validate_after_boot_converges(
    root: Path,
    *,
    wait_seconds: float = _BOOT_CONVERGENCE_SECONDS,
    poll_seconds: float = _BOOT_POLL_SECONDS,
    sleep: object = time.sleep,
):
    """Wait only for the Supervisor's fresh live state at logon.

    The two GUI tasks share the same logon trigger.  The validation task can
    therefore start first; retrying the live check avoids reporting the prior
    boot's PID as a failure while retaining a bounded failure for real faults.
    """
    runtime = validate_live_runtime(root)
    deadline = time.monotonic() + wait_seconds
    while (
        runtime.status != "pass"
        and _transient_boot_failure(tuple(runtime.failures))
        and time.monotonic() < deadline
    ):
        sleep(poll_seconds)
        runtime = validate_live_runtime(root)
    return runtime


def main(root: Path = ROOT) -> int:
    """Write a report based on fresh packaged validation, not legacy files."""

    runtime = _validate_after_boot_converges(root)
    runtime_path_findings = audit_runtime_paths(root)
    checks = dict(runtime.checks)
    checks["canonical_runtime_paths"] = not runtime_path_findings
    report = {
        "platform": "windows",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failures": list(runtime.failures),
        "supervisor_pid": runtime.supervisor_pid,
        "services": list(runtime.services),
        "managed_state_path": runtime.state_path,
        "runtime_path_findings": runtime_path_findings,
        "status": "pass" if runtime.status == "pass" and not runtime_path_findings else "fail",
    }
    report_path = REPORT if root == ROOT else root / "logs" / "post-reboot-validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
