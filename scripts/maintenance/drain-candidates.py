"""Drena a fila de conhecimento (FASE 2).

Processa os `knowledge_candidates` presos em status 'candidate' (normalizados
mas nunca promovidos — vazamento de uma execução anterior) e os 'held'
(governança: hypothesis aguarda drenagem, risk=high aguarda aprovação).

Respeita a governança:
  - 'candidate' verified+low  -> promove
  - 'candidate' hypothesis    -> hold (fila de revisão)
  - 'candidate' risk=high     -> hold (aprovação explícita)
  - 'held' hypothesis+low     -> promove após HELD_MIN_AGE_DAYS
  - 'held' risk=high          -> NÃO promove automaticamente (include_high_risk=False)

Uso: python scripts/maintenance/drain-candidates.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.auth import load_env

load_env()

import core.database as db
from core.knowledge.promotion import (
    _governance_action,
    _row_to_candidate,
    hold_candidate,
    promote_candidate,
    promote_held_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Apenas reporta, não escreve")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    conn = db.get_connection()
    db.ensure_migrations(conn)
    dry = args.dry_run

    # 1. Candidates presos em 'candidate'
    rows = conn.execute(
        "SELECT * FROM knowledge_candidates WHERE status='candidate' ORDER BY created_at, id"
    ).fetchall()
    if args.limit:
        rows = rows[: args.limit]
    print(f"[candidate] status='candidate': {len(rows)}")

    promoted = held = 0
    if not dry:
        for row in rows:
            candidate = _row_to_candidate(row)
            if _governance_action(candidate) == "hold":
                reason = ("risk=high aguardando revisão" if candidate.risk == "high"
                          else "confidence=hypothesis aguardando drenagem")
                hold_candidate(conn, candidate, reason=reason)
                held += 1
            else:
                try:
                    promote_candidate(conn, candidate)
                    promoted += 1
                except Exception as exc:
                    hold_candidate(conn, candidate, reason=f"erro na promoção: {exc}")
                    held += 1
        conn.commit()
        print(f"  -> promovidos: {promoted}, held: {held}")

    # 2. Fila 'held' (hypothesis+low após min_age; high-risk fica)
    held_before = conn.execute(
        "SELECT COUNT(*) FROM knowledge_candidates WHERE status='held'"
    ).fetchone()[0]
    print(f"[held] status='held': {held_before}")
    if not dry:
        report = promote_held_candidates(
            conn, include_high_risk=False, apply=True, limit=args.limit
        )
        print(f"  -> {report}")

    if dry:
        print("(dry-run — nada escrito)")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
