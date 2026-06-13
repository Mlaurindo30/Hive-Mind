#!/usr/bin/env python3
"""Consistent backup, restore and index recovery for the Hive-Mind UMC."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import struct
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "hive_mind.db"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.enable_load_extension(True)
    try:
        import sqlite_vec

        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name=? AND type IN ('table','view')",
            (table,),
        ).fetchone()
    )


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    result = {}
    for table in (
        "neurons",
        "synapses",
        "observations",
        "search_fts",
        "search_vec",
        "ambiguities",
        "visual_memories",
        "document_memories",
        "goals",
        "causal_edges",
    ):
        if table_exists(conn, table):
            result[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return result


def verify_database(db_path: Path) -> dict:
    conn = connect(db_path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        foreign_keys = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        current_counts = counts(conn)

        if table_exists(conn, "search_fts") and table_exists(conn, "neurons"):
            missing_fts = conn.execute(
                """
                SELECT COUNT(*) FROM neurons n
                WHERE NOT EXISTS (
                    SELECT 1 FROM search_fts f WHERE f.neuron_id=n.id
                )
                """
            ).fetchone()[0]
        else:
            missing_fts = None

        vector_probe = "not_available"
        if current_counts.get("search_vec", 0):
            row = conn.execute("SELECT embedding FROM search_vec LIMIT 1").fetchone()
            conn.execute(
                "SELECT neuron_id FROM search_vec WHERE embedding MATCH ? AND k=1",
                (row["embedding"],),
            ).fetchall()
            vector_probe = "ok"

        return {
            "db": str(db_path),
            "integrity_check": integrity,
            "quick_check": quick,
            "foreign_key_violations": foreign_keys,
            "counts": current_counts,
            "missing_fts": missing_fts,
            "vector_probe": vector_probe,
            "sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        }
    finally:
        conn.close()


def backup_database(db_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = output_dir / f"hive_mind.{stamp}.db"
    source = connect(db_path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    destination.chmod(0o600)

    report = verify_database(destination)
    (destination.with_suffix(".manifest.json")).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    return destination


def restore_database(backup_path: Path, target_path: Path) -> Path:
    backup_report = verify_database(backup_path)
    if backup_report["integrity_check"] != "ok":
        raise RuntimeError(f"backup integrity failure: {backup_report['integrity_check']}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target_path.name}.", dir=target_path.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        source = connect(backup_path)
        target = sqlite3.connect(temp_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

        if verify_database(temp_path)["integrity_check"] != "ok":
            raise RuntimeError("restored temporary database failed integrity_check")
        temp_path.chmod(0o600)
        os.replace(temp_path, target_path)
        for suffix in ("-wal", "-shm"):
            Path(f"{target_path}{suffix}").unlink(missing_ok=True)
        return target_path
    finally:
        temp_path.unlink(missing_ok=True)


def _default_embedder() -> Callable[[list[str]], Iterable[list[float]]]:
    from fastembed import TextEmbedding

    cache_dir = ROOT / "claude-mem" / "data" / "models"
    cache_dir.mkdir(parents=True, exist_ok=True)
    model = TextEmbedding(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        cache_dir=str(cache_dir),
    )
    return lambda texts: model.embed(texts)


def rebuild_indexes(
    db_path: Path,
    embed_batch: Callable[[list[str]], Iterable[list[float]]] | None = None,
) -> dict:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM search_fts")
        conn.execute(
            """
            INSERT INTO search_fts(neuron_id, label, content)
            SELECT id, label, COALESCE(content, '') FROM neurons
            """
        )

        rows = conn.execute(
            "SELECT id, COALESCE(content, label, '') AS text FROM neurons ORDER BY id"
        ).fetchall()
        embed_batch = embed_batch or _default_embedder()
        conn.execute("DELETE FROM search_vec")
        conn.execute("UPDATE neurons SET indexed_at=NULL")

        from core import hnsw_index

        hnsw_index._INDEX_PATH = db_path.parent / "hnsw_neurons.idx"
        hnsw_index._INDEX = None

        texts = [row["text"][:5000] for row in rows]
        vectors = list(embed_batch(texts)) if texts else []
        if len(vectors) != len(rows):
            raise RuntimeError(f"embedding count mismatch: {len(vectors)} != {len(rows)}")

        vectors_by_text = {}
        for text, vector in zip(texts, vectors):
            vectors_by_text.setdefault(text, list(vector))

        def vector_for(text: str) -> list[float]:
            return vectors_by_text[text[:5000]]

        for row, vector in zip(rows, vectors):
            packed = struct.pack(f"{len(vector)}f", *vector)
            conn.execute(
                "INSERT INTO search_vec(neuron_id, embedding) VALUES (?, ?)",
                (row["id"], packed),
            )

        hnsw_index.rebuild_from_db(conn, vector_for, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return verify_database(db_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    backup_cmd = sub.add_parser("backup")
    backup_cmd.add_argument("--db", type=Path, default=DEFAULT_DB)
    backup_cmd.add_argument("--output", type=Path, default=ROOT / "backups")

    restore_cmd = sub.add_parser("restore")
    restore_cmd.add_argument("backup", type=Path)
    restore_cmd.add_argument("--db", type=Path, default=DEFAULT_DB)
    restore_cmd.add_argument("--rebuild-indexes", action="store_true")

    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--db", type=Path, default=DEFAULT_DB)

    rebuild_cmd = sub.add_parser("rebuild-indexes")
    rebuild_cmd.add_argument("--db", type=Path, default=DEFAULT_DB)

    args = parser.parse_args()
    if args.command == "backup":
        path = backup_database(args.db.resolve(), args.output.resolve())
        print(path)
    elif args.command == "restore":
        restore_database(args.backup.resolve(), args.db.resolve())
        report = (
            rebuild_indexes(args.db.resolve())
            if args.rebuild_indexes
            else verify_database(args.db.resolve())
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.command == "verify":
        report = verify_database(args.db.resolve())
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["integrity_check"] == "ok" else 1
    elif args.command == "rebuild-indexes":
        print(json.dumps(rebuild_indexes(args.db.resolve()), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
