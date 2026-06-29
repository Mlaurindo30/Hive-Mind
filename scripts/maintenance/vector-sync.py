#!/usr/bin/env python3
"""K2 vector sync/backfill CLI: live SQLite collections -> Milvus.

This is the operator-facing wrapper around `core.vector_sync`. It handles all
K2 collections that are live today:
- memory_vectors: hive_mind.db/search_vec
- observation_vectors: claude-mem.db/vec_observations
- document_vectors/code_vectors/visual_vectors/graph_vectors/summary_vectors:
  hive_mind.db auxiliary sqlite-vec tables, with local backfill before sync.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.vector_backend import MilvusBackend
from core.vector_sync import (
    AUXILIARY_COLLECTIONS,
    backfill_auxiliary_vectors_to_sqlite,
    sync_auxiliary_vectors_to_milvus,
    sync_memory_vectors_to_milvus,
    sync_observation_vectors_to_milvus,
)

LIVE_COLLECTIONS = ("memory_vectors", "observation_vectors", *AUXILIARY_COLLECTIONS)


def _open_hive_db(path: str | None):
    import core.database as db

    if not path:
        conn = db.get_connection()
        db.ensure_migrations(conn)
        return conn

    db_path = Path(path).expanduser()
    if not db_path.exists():
        raise FileNotFoundError(f"hive_mind.db nao encontrado: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    try:
        import sqlite_vec

        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)
    db.ensure_migrations(conn)
    return conn


def _collections(values: Iterable[str] | None) -> list[str]:
    selected = list(values or LIVE_COLLECTIONS)
    unknown = [item for item in selected if item not in LIVE_COLLECTIONS]
    if unknown:
        known = ", ".join(LIVE_COLLECTIONS)
        raise ValueError(f"colecao K2 CLI nao suportada: {unknown}; suportadas: {known}")
    return selected


def run(args: argparse.Namespace) -> tuple[int, dict]:
    backend = MilvusBackend(uri=args.milvus_uri, collection_prefix=args.milvus_prefix)
    selected = _collections(args.collection)
    reports = []
    backfill_reports = []
    conn = None
    try:
        if "memory_vectors" in selected:
            conn = _open_hive_db(args.hive_db)
            reports.append(sync_memory_vectors_to_milvus(conn, backend, limit=args.limit))
        if "observation_vectors" in selected:
            reports.append(
                sync_observation_vectors_to_milvus(
                    args.claude_mem_db,
                    backend,
                    limit=args.limit,
                )
            )
        auxiliary = tuple(collection for collection in selected if collection in AUXILIARY_COLLECTIONS)
        if auxiliary:
            if conn is None:
                conn = _open_hive_db(args.hive_db)
            all_backfill_reports = backfill_auxiliary_vectors_to_sqlite(conn, limit=args.limit)
            backfill_by_collection = {report.collection: report for report in all_backfill_reports}
            backfill_reports.extend(backfill_by_collection[collection] for collection in auxiliary)
            reports.extend(
                sync_auxiliary_vectors_to_milvus(
                    conn,
                    backend,
                    collections=auxiliary,
                    limit=args.limit,
                )
            )
    finally:
        if conn is not None:
            conn.close()

    payload = {
        "backend": "milvus",
        "milvus_uri": backend.uri,
        "milvus_prefix": backend.collection_prefix,
        "backfill_reports": [asdict(report) for report in backfill_reports],
        "reports": [asdict(report) for report in reports],
    }
    exit_code = 1 if any(report.failed for report in [*backfill_reports, *reports]) else 0
    return exit_code, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection",
        action="append",
        choices=LIVE_COLLECTIONS,
        help="Colecao viva para sincronizar. Repita para multiplas. Default: ambas.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limita o lote; default faz backfill completo.")
    parser.add_argument("--hive-db", default=None, help="Override do hive_mind.db; default usa core.database.DB_PATH.")
    parser.add_argument(
        "--claude-mem-db",
        default=str(Path.home() / ".claude-mem" / "claude-mem.db"),
        help="Caminho do claude-mem.db com vec_observations.",
    )
    parser.add_argument("--milvus-uri", default=None, help="Override do MILVUS_URI.")
    parser.add_argument("--milvus-prefix", default=None, help="Prefixo das colecoes Milvus.")
    parser.add_argument("--json", action="store_true", help="Imprime payload JSON para automacao.")
    args = parser.parse_args(argv)

    try:
        exit_code, payload = run(args)
    except Exception as exc:
        error = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if args.json:
            print(json.dumps(error, ensure_ascii=False))
        else:
            print(error["error"], file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        for report in payload["backfill_reports"]:
            print(
                "backfill {collection}: scanned={scanned} upserted={upserted} "
                "skipped={skipped} failed={failed}".format(**report)
            )
            for error in report["errors"]:
                print(f"  ERROR {error}", file=sys.stderr)
        for report in payload["reports"]:
            print(
                "{collection}: scanned={scanned} upserted={upserted} "
                "skipped={skipped} failed={failed}".format(**report)
            )
            for error in report["errors"]:
                print(f"  ERROR {error}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
