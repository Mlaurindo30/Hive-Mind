"""Backfill de integridade de dados (FASE 2).

Corrige, de forma idempotente e não-destrutiva:
  1. observations.consumed_by = 'legacy'  quando archived=1 e consumed_by IS NULL
  2. observations.project      = 'unclassified' quando vazio
  3. neurons.topic             = derivado do source_file quando vazio mas com file

Uso: python scripts/maintenance/data-backfill.py [--dry-run]
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Apenas reporta, não escreve")
    args = parser.parse_args()

    conn = db.get_connection()
    db.ensure_migrations(conn)

    dry = args.dry_run

    # 1. consumed_by
    n_consumed = conn.execute(
        "SELECT COUNT(*) FROM observations WHERE archived=1 AND (consumed_by IS NULL OR consumed_by='')"
    ).fetchone()[0]
    print(f"[consumed_by] archived=1 com NULL: {n_consumed}")
    if not dry and n_consumed:
        conn.execute(
            "UPDATE observations SET consumed_by='legacy' "
            "WHERE archived=1 AND (consumed_by IS NULL OR consumed_by='')"
        )

    # 2. project
    n_proj = conn.execute(
        "SELECT COUNT(*) FROM observations WHERE project IS NULL OR TRIM(project)=''"
    ).fetchone()[0]
    print(f"[project] vazio: {n_proj}")
    if not dry and n_proj:
        conn.execute(
            "UPDATE observations SET project='unclassified' "
            "WHERE project IS NULL OR TRIM(project)=''"
        )

    # 3. neurons.topic derivado de source_file (cortex/temporal/<proj>/<topic>/...)
    n_topic = conn.execute(
        "SELECT COUNT(*) FROM neurons WHERE (topic IS NULL OR topic='') "
        "AND source_file IS NOT NULL AND source_file != ''"
    ).fetchone()[0]
    print(f"[topic] vazio com source_file: {n_topic}")
    if not dry and n_topic:
        rows = conn.execute(
            "SELECT id, source_file FROM neurons "
            "WHERE (topic IS NULL OR topic='') AND source_file IS NOT NULL AND source_file != ''"
        ).fetchall()
        updated = 0
        for rid, src in rows:
            parts = [p for p in src.replace("\\", "/").split("/") if p]
            topic = None
            if "temporal" in parts:
                idx = parts.index("temporal")
                if idx + 2 < len(parts):
                    topic = parts[idx + 2]
            elif len(parts) >= 3 and "neuronio-" not in parts[-1]:
                topic = parts[-2]
            if topic:
                conn.execute("UPDATE neurons SET topic=? WHERE id=?", (topic, rid))
                updated += 1
        print(f"  -> {updated} topics derivados")

    if not dry:
        conn.commit()
        print("Backfill aplicado.")
    else:
        print("(dry-run — nada escrito)")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
