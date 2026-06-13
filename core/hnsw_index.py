"""
HNSW incremental vector index for Hive-Mind neurons.

Depends on: hnswlib (optional). If not installed, all functions degrade gracefully
(log a warning and return empty results / no-op).
"""

import logging
import os
import json
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import hnswlib as _hnswlib
except ImportError:
    _hnswlib = None

# Index lives next to hive_mind.db
_INDEX_PATH: Optional[Path] = None
_INDEX = None  # hnswlib.Index or None
_DIM: int = int(os.environ.get("HNSW_DIM", "384"))

# Internal map: hnswlib integer label <-> neuron_id string
_id_to_label: dict[str, int] = {}
_label_to_id: dict[int, str] = {}
_next_label: int = 0


def _get_index_path() -> Path:
    """Derive index path from DB_PATH env or default."""
    global _INDEX_PATH
    if _INDEX_PATH is not None:
        return _INDEX_PATH
    try:
        from core.database import DB_PATH
        base = Path(DB_PATH).parent
    except Exception:
        base = Path(".")
    _INDEX_PATH = base / "hnsw_neurons.idx"
    return _INDEX_PATH


def _get_map_path() -> Path:
    return _get_index_path().with_suffix(".map.json")


def _load_id_map() -> None:
    global _id_to_label, _label_to_id, _next_label
    map_path = _get_map_path()
    if not map_path.exists():
        _id_to_label = {}
        _label_to_id = {}
        _next_label = 0
        return
    data = json.loads(map_path.read_text())
    _id_to_label = {str(k): int(v) for k, v in data.get("id_to_label", {}).items()}
    _label_to_id = {label: neuron_id for neuron_id, label in _id_to_label.items()}
    _next_label = max(_label_to_id, default=-1) + 1


def load_or_create(dim: int | None = None) -> bool:
    """Load existing index from disk or create a new one. Returns True on success."""
    global _INDEX, _DIM, _id_to_label, _label_to_id, _next_label

    if _hnswlib is None:
        logger.warning("hnswlib not installed — HNSW index unavailable")
        return False

    if dim is not None:
        _DIM = dim

    idx_path = _get_index_path()
    index = _hnswlib.Index(space="cosine", dim=_DIM)

    if idx_path.exists():
        try:
            index.load_index(str(idx_path), max_elements=0)
            _INDEX = index
            _load_id_map()
            if index.get_current_count() != len(_label_to_id):
                raise ValueError(
                    "HNSW index/map count mismatch: "
                    f"{index.get_current_count()} != {len(_label_to_id)}"
                )
            logger.debug("HNSW: loaded index from %s", idx_path)
            return True
        except Exception as exc:
            logger.warning("HNSW: failed to load index (%s) — creating fresh", exc)

    try:
        index.init_index(max_elements=10_000, ef_construction=200, M=16)
        index.set_ef(50)
        _INDEX = index
        _id_to_label = {}
        _label_to_id = {}
        _next_label = 0
        logger.debug("HNSW: created new index (dim=%d)", _DIM)
        return True
    except Exception as exc:
        logger.error("HNSW: could not create index: %s", exc)
        return False


def _save_index() -> None:
    """Persist index and label map with atomic replacements."""
    if _INDEX is None:
        return
    idx_tmp = None
    map_tmp = None
    try:
        idx_path = _get_index_path()
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        idx_fd, idx_name = tempfile.mkstemp(
            prefix=f".{idx_path.name}.", dir=idx_path.parent
        )
        os.close(idx_fd)
        idx_tmp = Path(idx_name)
        map_path = _get_map_path()
        map_fd, map_name = tempfile.mkstemp(
            prefix=f".{map_path.name}.", dir=map_path.parent
        )
        os.close(map_fd)
        map_tmp = Path(map_name)

        _INDEX.save_index(str(idx_tmp))
        map_tmp.write_text(
            json.dumps({"id_to_label": _id_to_label}, sort_keys=True) + "\n"
        )
        os.replace(idx_tmp, idx_path)
        os.replace(map_tmp, map_path)
    except Exception as exc:
        logger.warning("HNSW: could not save index: %s", exc)
        raise
    finally:
        if idx_tmp is not None:
            idx_tmp.unlink(missing_ok=True)
        if map_tmp is not None:
            map_tmp.unlink(missing_ok=True)


def add_neuron(neuron_id: str, vector: list[float], conn=None) -> bool:
    """Add/update a neuron's vector. Updates indexed_at in DB if conn provided. Returns True on success."""
    global _INDEX, _id_to_label, _label_to_id, _next_label

    if _hnswlib is None or _INDEX is None:
        return False

    try:
        if neuron_id in _id_to_label:
            label = _id_to_label[neuron_id]
        else:
            label = _next_label
            _next_label += 1
            _id_to_label[neuron_id] = label
            _label_to_id[label] = neuron_id

        current_count = _INDEX.get_current_count()
        max_elements = _INDEX.get_max_elements()
        if current_count >= max_elements:
            _INDEX.resize_index(max_elements + 10_000)

        _INDEX.add_items([vector], [label])

        if conn is not None:
            conn.execute(
                "UPDATE neurons SET indexed_at=CURRENT_TIMESTAMP WHERE id=?",
                (neuron_id,),
            )

        return True
    except Exception as exc:
        logger.warning("HNSW: add_neuron failed for %s: %s", neuron_id, exc)
        return False


def search(query_vector: list[float], k: int = 10) -> list[dict]:
    """Return top-k neighbors: [{"neuron_id": str, "distance": float}]"""
    if _hnswlib is None or _INDEX is None:
        return []

    try:
        count = _INDEX.get_current_count()
        if count == 0:
            return []
        actual_k = min(k, count)
        labels, distances = _INDEX.knn_query([query_vector], k=actual_k)
        results = []
        for label, dist in zip(labels[0], distances[0]):
            nid = _label_to_id.get(int(label))
            if nid is not None:
                results.append({"neuron_id": nid, "distance": float(dist)})
        return results
    except Exception as exc:
        logger.warning("HNSW: search failed: %s", exc)
        return []


def rebuild_from_db(conn, embed_fn, *, commit: bool = True) -> int:
    """Rebuild full index from all neurons using embed_fn(text) -> list[float]. Returns count indexed."""
    global _INDEX, _id_to_label, _label_to_id, _next_label

    if _hnswlib is None:
        return 0

    rows = conn.execute("SELECT id, content FROM neurons WHERE content IS NOT NULL").fetchall()
    if not rows:
        return 0

    _INDEX = _hnswlib.Index(space="cosine", dim=_DIM)
    _INDEX.init_index(max_elements=max(len(rows), 100), ef_construction=200, M=16)
    _INDEX.set_ef(50)
    _id_to_label = {}
    _label_to_id = {}
    _next_label = 0

    count = 0
    for row in rows:
        nid = row[0] if isinstance(row, (list, tuple)) else row["id"]
        content = row[1] if isinstance(row, (list, tuple)) else row["content"]
        try:
            vec = embed_fn(content)
            add_neuron(nid, vec, conn=conn)
            count += 1
        except Exception as exc:
            logger.warning("HNSW: rebuild skipped neuron %s: %s", nid, exc)

    _save_index()
    if commit:
        conn.commit()
    return count


def rebuild_from_vectors(
    conn,
    vectors: dict[str, list[float]],
    *,
    commit: bool = True,
) -> int:
    """Rebuild the complete index from canonical vectors keyed by neuron ID."""
    global _INDEX, _id_to_label, _label_to_id, _next_label

    if _hnswlib is None or not vectors:
        return 0
    _INDEX = _hnswlib.Index(space="cosine", dim=_DIM)
    _INDEX.init_index(max_elements=max(len(vectors), 100), ef_construction=200, M=16)
    _INDEX.set_ef(50)
    _id_to_label = {}
    _label_to_id = {}
    _next_label = 0

    count = 0
    for neuron_id, vector in vectors.items():
        if add_neuron(neuron_id, vector, conn=conn):
            count += 1
    _save_index()
    if commit:
        conn.commit()
    return count


def incremental_update(conn, embed_fn, *, commit: bool = True) -> int:
    """Index neurons where indexed_at IS NULL. Returns count newly indexed."""
    if _hnswlib is None:
        return 0

    if _INDEX is None:
        load_or_create()

    rows = conn.execute(
        "SELECT id, content FROM neurons WHERE indexed_at IS NULL AND content IS NOT NULL"
    ).fetchall()

    count = 0
    for row in rows:
        nid = row[0] if isinstance(row, (list, tuple)) else row["id"]
        content = row[1] if isinstance(row, (list, tuple)) else row["content"]
        try:
            vec = embed_fn(content)
            if add_neuron(nid, vec, conn=conn):
                count += 1
        except Exception as exc:
            logger.warning("HNSW: incremental_update skipped neuron %s: %s", nid, exc)

    if count > 0:
        _save_index()
        if commit:
            conn.commit()

    return count


def upsert_vectors(
    conn,
    vectors: dict[str, list[float]],
    *,
    commit: bool = True,
) -> int:
    """Add or replace already-computed vectors and persist the index."""
    if _hnswlib is None or not vectors:
        return 0
    if _INDEX is None and not load_or_create():
        return 0

    count = 0
    for neuron_id, vector in vectors.items():
        if add_neuron(neuron_id, vector, conn=conn):
            count += 1
    if count:
        _save_index()
        if commit:
            conn.commit()
    return count
