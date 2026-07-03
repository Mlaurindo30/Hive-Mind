"""R3.5 — K8 production-readiness gate.

Spec: specs/post-audit-stabilization.md R3.5.

Exits non-zero if any of the following holds:
  - neurons_vectorized_pct < 99
  - orphan_vectors > 0
  - vectors_model_mismatch > 0

Run with:

    .venv/bin/python scripts/health/k8_gate.py
    .venv/bin/python scripts/health/k8_gate.py --json    # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database import get_connection, ensure_migrations


THRESHOLD = 99.0  # spec R3.5: neurons_vectorized_pct >= 99


def _metrics(conn) -> Dict[str, Any]:
    neurons_total = conn.execute("SELECT COUNT(*) FROM neurons").fetchone()[0]
    vec_neurons = conn.execute("SELECT COUNT(*) FROM search_vec").fetchone()[0]
    pct = (vec_neurons * 100.0 / neurons_total) if neurons_total else 0.0

    orphan_vectors = conn.execute(
        """
        SELECT COUNT(*) FROM vec_documents v
        WHERE NOT EXISTS (SELECT 1 FROM document_chunks c WHERE c.id = v.chunk_id)
        """
    ).fetchone()[0]

    # vectors_model_mismatch: rows whose `embedding_model` column does not
    # match the canonical 'snowflake-arctic-embed2:latest'. The column may
    # be NULL; treat NULL as match (it is the canonical value when the
    # embedder wrote the row before the field was added).
    total_vec_metadata = conn.execute("SELECT COUNT(*) FROM vector_metadata").fetchone()[0]
    bad_model = conn.execute(
        """
        SELECT COUNT(*) FROM vector_metadata
        WHERE embedding_model IS NOT NULL
          AND embedding_model != 'snowflake-arctic-embed2:latest'
        """
    ).fetchone()[0] if conn.execute(
        "SELECT 1 FROM pragma_table_info('vector_metadata') WHERE name = 'embedding_model'"
    ).fetchone() else 0

    return {
        "neurons_total": neurons_total,
        "neurons_vectorized": vec_neurons,
        "neurons_vectorized_pct": round(pct, 2),
        "orphan_vectors": orphan_vectors,
        "vectors_model_mismatch": bad_model,
        "vector_metadata_total": total_vec_metadata,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="K8 production-readiness gate (R3.5)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--threshold", type=float, default=THRESHOLD,
                        help="minimum neurons_vectorized_pct (default: 99)")
    args = parser.parse_args()

    conn = get_connection()
    try:
        ensure_migrations(conn)
        m = _metrics(conn)
    finally:
        conn.close()

    failures: list[str] = []
    if m["neurons_vectorized_pct"] < args.threshold:
        failures.append(
            f"neurons_vectorized_pct={m['neurons_vectorized_pct']} < {args.threshold}"
        )
    if m["orphan_vectors"] > 0:
        failures.append(f"orphan_vectors={m['orphan_vectors']} > 0")
    if m["vectors_model_mismatch"] > 0:
        failures.append(f"vectors_model_mismatch={m['vectors_model_mismatch']} > 0")

    m["threshold"] = args.threshold
    m["failures"] = failures
    m["gate_passed"] = len(failures) == 0

    if args.json:
        print(json.dumps(m, indent=2, sort_keys=True))
    else:
        for k in ("neurons_total", "neurons_vectorized", "neurons_vectorized_pct",
                  "orphan_vectors", "vectors_model_mismatch", "vector_metadata_total",
                  "threshold", "gate_passed"):
            print(f"{k}: {m[k]}")
        if failures:
            for f in failures:
                print(f"  FAIL: {f}")
        else:
            print("K8 gate: PASS")

    return 0 if m["gate_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
