#!/usr/bin/env python3
"""Windows post-reboot validation; never depends on systemd or procfs."""
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

try:
    from scripts.health.audit_runtime_paths_windows import audit_runtime_paths
except ModuleNotFoundError:  # Direct script execution adds scripts/health to sys.path.
    from audit_runtime_paths_windows import audit_runtime_paths

REPORT = ROOT / "logs" / "post-reboot-validation.json"


def task_exists(name: str) -> bool:
    return subprocess.run(
        ["schtasks", "/Query", "/TN", name], capture_output=True, text=True
    ).returncode == 0


def load_state(root: Path = ROOT, timeout: int = 120) -> dict:
    path = root / "logs" / "supervisor" / "state.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = json.loads(path.read_text())
            if state:
                return state
        except Exception:
            pass
        time.sleep(2)
    return {}


def installation_profile(root: Path = ROOT) -> str:
    try:
        for line in (root / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("HIVE_MIND_PROFILE="):
                return line.split("=", 1)[1].strip().strip('"\'') or "local-min"
    except OSError:
        pass
    return "local-min"


def load_manifest(root: Path = ROOT) -> dict:
    try:
        return json.loads((root / "logs" / "supervisor" / "manifest.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def required_service_names(manifest: dict, profile: str) -> list[str]:
    return [
        service["name"]
        for service in manifest.get("services", [])
        if service.get("required")
        and profile in service.get("enabled_profiles", ["local-min", "local-full"])
    ]


def assess_required_services(state: dict, required_services: list[str]) -> tuple[bool, list[str]]:
    unhealthy = [
        name for name in required_services if state.get(name, {}).get("state") != "healthy"
    ]
    return not unhealthy, unhealthy


def main() -> int:
    state = load_state()
    manifest = load_manifest()
    profile = installation_profile()
    required_services = required_service_names(manifest, profile)
    services_healthy, unhealthy_services = assess_required_services(
        state, required_services
    )
    runtime_path_findings = audit_runtime_paths(ROOT)
    checks = {
        "scheduled_supervisor": task_exists("HiveMind-Supervisor"),
        "supervisor_state_present": bool(state),
        "supervisor_manifest_present": bool(manifest),
        "required_services_declared": bool(required_services),
        "services_healthy": services_healthy,
        "canonical_runtime_paths": not runtime_path_findings,
    }
    report = {
        "platform": "windows",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "checks": checks,
        "required_services": required_services,
        "unhealthy_required_services": unhealthy_services,
        "services": state,
        "runtime_path_findings": runtime_path_findings,
        "status": "pass" if all(checks.values()) else "fail",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
