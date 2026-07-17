from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "health" / "test_sinapse_tools_stdio.py"


def test_stdio_health_script_supports_a_cp1252_console():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--tool", "sinapse_health"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr.decode("cp1252", errors="replace")
    output = result.stdout.decode("cp1252", errors="strict")
    assert "[OK]" in output
    assert "\u2705" not in output
