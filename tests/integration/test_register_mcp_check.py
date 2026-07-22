"""`register-mcp --check` — the exit-code contract, restated (D009-R6).

Spec R5.4 (`specs/post-audit-stabilization.md`) said `--check` must exit 0
"regardless of how many agents are installed". That was true of the old
script, which reported what it found and always succeeded. It made `--check`
useless as a gate: an installation where nothing was registered passed.

D009-R6 routes `--check` to the one diagnosis implementation, and the
contract is now the one the delivery brief defines:

    0        every *detected* provider is fully configured
    non-zero the diagnosis is incomplete — something detected is unconfigured

A provider that is not installed is not a failure: there is nothing to
configure for an absent agent, and `ProviderDiagnosis.healthy` says so. So a
fresh machine with no agents still exits 0; a machine with agents that were
never registered exits non-zero, which is the honest answer and the reason
the old contract was replaced.

This test asserts the contract holds *on this machine* by deriving the
expected exit code from the diagnosis itself, rather than hardcoding a value
that only happens to match today's host.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


def _wrapper_command() -> list[str]:
    if os.name == "nt":
        if not POWERSHELL:
            pytest.skip("powershell not available")
        return [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", "scripts/setup/register-mcp.ps1", "--check"]
    if not BASH:
        pytest.skip("bash not available")
    return [BASH, "scripts/setup/register-mcp.sh", "--check"]


def _run(command: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env['PATH']}"
    return subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=300, env=env)


def _expected_exit_code() -> int:
    """What the diagnosis says the answer should be, computed independently."""
    from hive_mind.agents.doctor import diagnose

    home = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
    appdata = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
    report = diagnose(home=home, appdata=appdata, project_root=PROJECT_ROOT)
    return 0 if all(d.healthy for d in report) else 1


def test_check_exit_code_matches_the_diagnosis():
    proc = _run(_wrapper_command())
    assert proc.returncode == _expected_exit_code(), (
        f"--check exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
    )


def test_check_reports_every_detected_provider():
    """The output must name what it judged, not just deliver a verdict."""
    from hive_mind.agents.detect import detect_providers

    detected = [r.id for r in detect_providers() if r.detected]
    if not detected:
        pytest.skip("no agent installed on this machine (fresh/CI install)")
    proc = _run(_wrapper_command())
    missing = [name for name in detected if name not in proc.stdout]
    assert missing == [], f"--check did not report {missing}:\n{proc.stdout}"


def test_check_writes_nothing():
    """A diagnosis that modified configs would not be a diagnosis."""
    home = Path(os.path.expanduser("~"))
    watched = [home / ".codex" / "config.toml", home / ".claude.json",
               home / ".qwen" / "settings.json"]
    before = {p: p.stat().st_mtime_ns for p in watched if p.exists()}
    _run(_wrapper_command())
    after = {p: p.stat().st_mtime_ns for p in watched if p.exists()}
    assert before == after
