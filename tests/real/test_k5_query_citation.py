from __future__ import annotations

import pytest

pytestmark = pytest.mark.real

"""R10.3 — sinapse_query returns citation for synthesis terms.

Spec: specs/post-audit-stabilization.md R10.3.

After R10.1 has run, sinapse_query for terms that appear in a
generated synthesis MUST return a citation whose source_uri points
to the corresponding synthesis file under cerebro/cerebelo/.
"""
import json
import subprocess
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
def test_query_for_synthesis_term_returns_citation():
    proc = subprocess.run(
        [".venv/bin/python", "scripts/services/sinapse-write.py", "query",
         "síntese semanal"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"query failed: {proc.stderr}"
    # The response is JSON (with leading log lines on stderr; stdout is
    # the JSON payload). Parse from the first '{' onward.
    out = proc.stdout
    payload = json.loads(out[out.find("{"):])
    hits = payload.get("answer_context") or []
    assert hits, f"no answer_context for 'síntese semanal': {payload}"
    synthesis_hits = [
        h for h in hits
        if (h.get("source_uri") or "").startswith("cerebelo/")
    ]
    assert synthesis_hits, (
        f"no hit cites a cerebro/cerebelo/ synthesis file. "
        f"hits: {[h.get('source_uri') for h in hits]}"
    )
