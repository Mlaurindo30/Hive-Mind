from __future__ import annotations

import pytest

pytestmark = pytest.mark.real


"""R11.2 — Disaster recovery: a copy of cerebro/ + hive_mind.db is queryable.

Spec: specs/post-audit-stabilization.md R11.2.

Builds `/tmp/hive-mind-recovery-test/` with copies of `cerebro/` and
`hive_mind.db`, runs `recover.sh verify` against the live DB, and
runs a vector/fts sanity check against the copy via the .venv (so
sqlite-vec is loaded).
"""
import shutil
import subprocess
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RECOVERY_ROOT = Path("/tmp/hive-mind-recovery-test")
def _venv_python() -> str:
    return str(PROJECT_ROOT / ".venv" / "bin" / "python")
def test_recover_sh_verify_passes():
    """recover.sh verify on the live DB exits 0 with no FK violations."""
    proc = subprocess.run(
        ["bash", "scripts/utils/recover.sh", "verify"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, (
        f"recover.sh verify failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert '"foreign_key_violations": 0' in proc.stdout
    assert '"integrity_check": "ok"' in proc.stdout
def test_recovery_copy_is_queryable():
    """A /tmp copy of cerebro/ + hive_mind.db MUST have populated
    search_vec and search_fts, queryable through the .venv.
    """
    if RECOVERY_ROOT.exists():
        shutil.rmtree(RECOVERY_ROOT)
    RECOVERY_ROOT.mkdir(parents=True)

    shutil.copytree(PROJECT_ROOT / "cerebro", RECOVERY_ROOT / "cerebro")
    shutil.copy(PROJECT_ROOT / "hive_mind.db", RECOVERY_ROOT / "hive_mind.db")

    proc = subprocess.run(
        [_venv_python(), "scripts/health/recovery_check.py",
         str(RECOVERY_ROOT / "hive_mind.db")],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
    )
    if "no-vec" in proc.stdout:
        pytest.skip(f"sqlite_vec not loadable: {proc.stdout}")
    assert proc.returncode == 0, (
        f"recovery copy query failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    out = proc.stdout.strip()
    assert "vec 0" not in out, f"vec table empty in recovery copy: {out}"
    assert "fts 0" not in out, f"fts table empty in recovery copy: {out}"

    shutil.rmtree(RECOVERY_ROOT)
# pytest import (declared at function level to keep this helper importable)
