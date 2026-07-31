from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_windows_runtime_dry_run_cli_does_not_require_watchdog_report_field():
    result = subprocess.run(
        [
            str(ROOT / ".venv" / "Scripts" / "python.exe"),
            "-m",
            "hive_mind.cli",
            "service",
            "windows-runtime",
            "--project-root",
            str(ROOT),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "HiveMind-Supervisor" in result.stdout
    assert "startup_watchdog_path" not in result.stdout
