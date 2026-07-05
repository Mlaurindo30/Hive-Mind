from __future__ import annotations

import pytest

pytestmark = pytest.mark.real


"""R10 — K5 cadence scripts produce non-empty outputs and summary_vectors.

Spec: specs/post-audit-stabilization.md R10.1, R10.2.

Runs the six cadence scripts (session_consolidator, daily_writer,
weekly_synthesizer, monthly_synthesizer, yearly_synthesizer,
pattern_distiller) and verifies the expected outputs exist and are
non-empty, and that summary_vectors has rows.
"""
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Each cadence runs in its own test so a slow one does not block the
# cheap ones. pattern_distiller can take minutes; it gets its own
# generous timeout.
CADENCES = [
    (["scripts/dream/session_consolidator.py", "--real"],
     "cerebro/cerebelo/sessoes", 60, "test_session_consolidator"),
    (["scripts/dream/daily_writer.py", "--date", __import__("datetime").date.today().isoformat()],
     "cerebro/cerebelo/diario", 60, "test_daily_writer"),
    (["scripts/dream/weekly_synthesizer.py", "--real"],
     "cerebro/cerebelo/semanal", 180, "test_weekly_synthesizer"),
    (["scripts/dream/monthly_synthesizer.py", "--real"],
     "cerebro/cerebelo/mensal", 180, "test_monthly_synthesizer"),
    (["scripts/dream/yearly_synthesizer.py", "--real"],
     "cerebro/cerebelo/anual", 180, "test_yearly_synthesizer"),
    (["scripts/knowledge/pattern_distiller.py", "--apply", "--since-days", "7"],
     "cerebro/cerebelo/padroes/Patterns.md", 600, "test_pattern_distiller"),
]
def _run(cmd: list[str], timeout: int) -> None:
    proc = subprocess.run(
        [".venv/bin/python", *cmd], cwd=PROJECT_ROOT,
        capture_output=True, text=True, timeout=timeout,
    )
    assert proc.returncode == 0, (
        f"cadence failed: {cmd}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
def _assert_outputs_present(expected: str) -> None:
    target = PROJECT_ROOT / expected
    assert target.exists(), f"missing {target}"
    if expected.endswith("Patterns.md"):
        assert target.read_text(encoding="utf-8").strip(), f"{target} is empty"
    else:
        entries = list(target.rglob("*.md"))
        assert entries, f"{target} produced no .md files"
@pytest.mark.parametrize("cmd,expected,timeout,testname", CADENCES,
                         ids=[c[3] for c in CADENCES])
def test_cadence_produces_outputs(cmd, expected, timeout, testname):
    _run(cmd, timeout)
    _assert_outputs_present(expected)
def test_summary_vectors_grew():
    """R10.2: summary_vectors MUST have rows."""
    from core.database import get_connection
    conn = get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM vector_metadata WHERE collection = 'summary_vectors'"
        ).fetchone()[0]
        assert n > 0, f"summary_vectors has {n} rows; expected > 0 after R10.1"
    finally:
        conn.close()
