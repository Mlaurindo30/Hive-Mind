"""R3.5 — K8 production gate exits 0 when thresholds are met.

Spec: specs/post-audit-stabilization.md R3.5.

Runs `scripts/health/k8_gate.py --json` against the live database and
asserts the gate reports `gate_passed: true`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_k8_gate_passes():
    proc = subprocess.run(
        [".venv/bin/python", "scripts/health/k8_gate.py", "--json"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, (
        f"k8_gate failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    payload = json.loads(proc.stdout)
    assert payload["gate_passed"] is True, f"gate reports failure: {payload}"
    assert payload["neurons_vectorized_pct"] >= 99, payload
    assert payload["orphan_vectors"] == 0, payload
    assert payload["vectors_model_mismatch"] == 0, payload
