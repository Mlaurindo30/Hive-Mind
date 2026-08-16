#!/usr/bin/env python3
"""Backfill: promove o candidato `decision` que faltou para observações type=decision
já consumidas pelo K3 antes do fix do intake (2026-08-14).

Antes do fix, uma observação `type=decision` com `facts` era promovida inteiramente
como `fact` (o `content` principal nunca virava candidato `decision`). Resultado:
o decision_promoter (que só lê neurônios type=decision) nunca materializava as
decisões reais no frontal. Este backfill re-normaliza cada observação afetada e
promove apenas o candidato `decision` resultante, sem tocar nos `fact` satélites.

Idempotente: pula observações que já têm neurônio type=decision vinculado.
--apply escreve; sem --apply é dry-run (só conta).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from core.knowledge.intake import normalize_observation  # noqa: E402
from core.knowledge.promotion import (  # noqa: E402
    _governance_action,
    promote_candidate,
    store_candidates,
)
from core.knowledge.intake import MemoryReadEcho, StructuralIntakeError  # noqa: E402


def _affected(conn) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT * FROM observations o
        WHERE o.type = 'decision'
          AND COALESCE(o.archived, 0) = 1
          AND NOT EXISTS (
              SELECT 1 FROM neurons n WHERE n.id = o.neuron_id AND n.type = 'decision'
          )
        ORDER BY o.created_at
        """
    ).fetchall()


def run(conn, *, apply: bool) -> dict[str, int]:
    rows = _affected(conn)
    stats = {"total": len(rows), "decision_candidates": 0, "promoted": 0,
             "skipped_no_decision": 0, "held": 0, "quarantined": 0, "echo": 0}
    for row in rows:
        obs_id = str(row["id"])
        try:
            candidates = normalize_observation(row)
        except MemoryReadEcho:
            stats["echo"] += 1
            continue
        except StructuralIntakeError:
            stats["quarantined"] += 1
            continue
        decision_cands = [c for c in candidates if c.knowledge_type == "decision"]
        if not decision_cands:
            stats["skipped_no_decision"] += 1
            continue
        stats["decision_candidates"] += len(decision_cands)
        for cand in decision_cands:
            if not apply:
                stats["promoted"] += 1
                continue
            if _governance_action(cand) == "hold":
                stats["held"] += 1
                continue
            store_candidates(conn, [cand])
            neuron_id = promote_candidate(conn, cand)
            if neuron_id:
                conn.execute(
                    "UPDATE observations SET neuron_id = ? WHERE id = ? AND neuron_id IS NULL",
                    (neuron_id, obs_id),
                )
                stats["promoted"] += 1
    if apply:
        conn.commit()
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill de decisões mal-classificadas como fact.")
    ap.add_argument("--db", default=r"D:\Hive-Mind\hive_mind.db")
    ap.add_argument("--apply", action="store_true", help="escreve (default: dry-run)")
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA busy_timeout=5000")
    stats = run(conn, apply=args.apply)
    print(f"backfill_decision: {stats}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
