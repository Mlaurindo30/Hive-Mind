#!/usr/bin/env python3
"""Build the HNSW index from canonical sqlite-vec embeddings."""

from __future__ import annotations

import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.database import get_connection
from core.hnsw_index import rebuild_from_vectors


def build(conn) -> int:
    rows = conn.execute(
        "SELECT neuron_id, embedding FROM search_vec"
    ).fetchall()
    vectors = {
        row["neuron_id"]: list(
            struct.unpack(f"{len(row['embedding']) // 4}f", row["embedding"])
        )
        for row in rows
    }
    if not vectors:
        raise RuntimeError("search_vec is empty; graph/vector indexing must run first")

    neuron_rows = conn.execute("SELECT id FROM neurons ORDER BY id").fetchall()
    missing = [row["id"] for row in neuron_rows if row["id"] not in vectors]
    if missing:
        raise RuntimeError(f"{len(missing)} neurons are missing canonical vectors")

    ordered_vectors = {row["id"]: vectors[row["id"]] for row in neuron_rows}
    return rebuild_from_vectors(conn, ordered_vectors)


def main() -> int:
    conn = get_connection()
    try:
        count = build(conn)
    finally:
        conn.close()
    print(f"HNSW rebuilt from sqlite-vec: {count} neurons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
