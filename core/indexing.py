"""Canonical sqlite-vec and HNSW indexing for selected neurons."""

from __future__ import annotations

from collections.abc import Iterable

from core.database import get_embedder, serialize_f32
from core.hnsw_index import upsert_vectors


def upsert_search_vec(conn, neuron_id: str, embedding_blob) -> None:
    """Canonical sqlite-vec write path.

    Some sqlite-vec builds do not behave reliably with INSERT OR REPLACE on
    virtual tables that declare a PRIMARY KEY. Delete then insert is explicit
    and avoids UNIQUE constraint failures during reindex.
    """
    conn.execute("DELETE FROM search_vec WHERE neuron_id = ?", (neuron_id,))
    conn.execute(
        "INSERT INTO search_vec(neuron_id, embedding) VALUES (?, ?)",
        (neuron_id, embedding_blob),
    )


def index_neuron_ids(conn, neuron_ids: Iterable[str], *, commit: bool = True) -> int:
    ids = list(dict.fromkeys(str(item) for item in neuron_ids))
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT id, COALESCE(content, label, '') AS text
        FROM neurons
        WHERE id IN ({placeholders})
        ORDER BY id
        """,
        ids,
    ).fetchall()
    if not rows:
        return 0

    embedder = get_embedder()
    if embedder is None:
        raise RuntimeError(
            "Nenhum backend de embedding disponível. "
            "Instale fastembed ou configure EMBED_BACKEND=ollama."
        )
    texts = [row["text"][:5000] for row in rows]
    vectors = [list(vector) for vector in embedder.embed(texts)]
    if len(vectors) != len(rows):
        raise RuntimeError(f"embedding count mismatch: {len(vectors)} != {len(rows)}")

    by_id = {}
    for row, vector in zip(rows, vectors):
        upsert_search_vec(conn, row["id"], serialize_f32(vector))
        by_id[row["id"]] = vector

    indexed = upsert_vectors(conn, by_id, commit=False)
    if indexed != len(rows):
        raise RuntimeError(f"HNSW indexed {indexed} of {len(rows)} neurons")
    if commit:
        conn.commit()
    return indexed
