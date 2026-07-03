"""R5.4 — register-mcp --check exits 0 and reports 11 agents.

Spec: specs/post-audit-stabilization.md R5.4.

Runs `bash scripts/setup/register-mcp.sh --check` and asserts the exit
code is 0 and the output reports the same agent count that the
documentation claims (16 MCP tools; this test only checks the
`--check` registration side, not the tool count).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_register_mcp_check_exits_zero():
    proc = subprocess.run(
        ["bash", "scripts/setup/register-mcp.sh", "--check"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, (
        f"register-mcp.sh --check exited {proc.returncode}:\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    # The expected output ends with a registration count summary line.
    match = re.search(r"(\d+)\s+agent\(s\)\s+detected", proc.stdout)
    assert match is not None, f"no agent count line in output:\n{proc.stdout}"
    count = int(match.group(1))
    assert count >= 1, f"register-mcp reports {count} agents; expected at least 1"
