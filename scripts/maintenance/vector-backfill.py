"""Backfill de vetorização: indexa neurônios ausentes do search_vec (sqlite-vec).

Uso:
  python scripts/maintenance/vector-backfill.py [--limit N] [--batch B]

Corrige o gap de ~32% de neurônios não-vetorizados (fora do índice semântico).
Usa o caminho canônico core.indexing.index_neuron_ids (embed + search_vec + HNSW).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.auth import load_env

load_env()

import core.database as db
from core.indexing import index_neuron_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Máximo de neurônios a indexar (default: todos)")
    parser.add_argument("--batch", type=int, default=200, help="Tamanho do lote de embedding")
    args = parser.parse_args()

    conn = db.get_connection()
    db.ensure_migrations(conn)

    # Set-difference em memória (NOT EXISTS sobre virtual table é O(n^2)).
    vectorized = {r[0] for r in conn.execute("SELECT neuron_id FROM search_vec")}
    all_ids = [r[0] for r in conn.execute(
        "SELECT id FROM neurons WHERE content IS NOT NULL ORDER BY id"
    )]
    ids = [nid for nid in all_ids if nid not in vectorized]
    total_missing = len(ids)
    print(f"Neurônios fora do search_vec: {total_missing}")

    if total_missing == 0:
        print("Nada a fazer.")
        return 0

    if args.limit:
        ids = ids[: args.limit]
    print(f"Indexando {len(ids)} neurônios (batch={args.batch})...")

    start = time.monotonic()
    done = 0
    failed = 0
    for i in range(0, len(ids), args.batch):
        chunk = ids[i:i + args.batch]
        try:
            n = index_neuron_ids(conn, chunk, commit=True)
            done += n
        except Exception as exc:
            failed += len(chunk)
            print(f"  [ERRO] lote {i}-{i + len(chunk)}: {type(exc).__name__}: {exc}")
        if done % 2000 < args.batch:
            print(f"  progresso: {done}/{len(ids)} indexados, {failed} falhas "
                  f"({time.monotonic() - start:.0f}s)")

    print(f"Concluído: {done} indexados, {failed} falhas em {time.monotonic() - start:.0f}s")
    conn.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
