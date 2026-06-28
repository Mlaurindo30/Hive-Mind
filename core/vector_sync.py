"""Vector sync/backfill helpers for K2.

Live sync paths:
- `memory_vectors`: local `hive_mind.db/search_vec` -> Milvus.
- `observation_vectors`: global/local `claude-mem.db/vec_observations` -> Milvus.

Other collections remain planned until their tables/backfill pipelines exist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
from typing import Any

from core.vector_backend import MilvusBackend, VectorBackend
from core.vector_collections import EMBED_DIM


@dataclass
class VectorSyncReport:
    collection: str
    scanned: int = 0
    upserted: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _decode_f32(blob: bytes | memoryview) -> list[float]:
    data = bytes(blob)
    if len(data) % 4 != 0:
        raise ValueError(f"embedding blob invalido: {len(data)} bytes")
    dim = len(data) // 4
    if dim != EMBED_DIM:
        raise ValueError(f"embedding com {dim}d; esperado {EMBED_DIM}d")
    return list(struct.unpack(f"{dim}f", data))


def _metadata_json(row: Any) -> dict[str, Any]:
    raw = row["metadata"] if "metadata" in row.keys() else None
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _project_from_source(source_file: str, metadata: dict[str, Any]) -> str:
    if metadata.get("project"):
        return str(metadata["project"])
    parts = source_file.replace("\\", "/").split("/")
    if "temporal" in parts:
        idx = parts.index("temporal")
        if idx + 1 < len(parts) and parts[idx + 1]:
            return parts[idx + 1]
    return "default"


def _brain_lobe_from_source(source_file: str) -> str:
    parts = source_file.replace("\\", "/").split("/")
    for lobe in ("temporal", "frontal", "parietal", "occipital", "insula"):
        if lobe in parts:
            return lobe
    if "diencefalo" in parts:
        return "diencefalo"
    if "cerebelo" in parts:
        return "cerebelo"
    if "tronco" in parts:
        return "tronco"
    return "temporal"


def _stable_hash(row: Any) -> str:
    if row["hash"]:
        return str(row["hash"])
    payload = "|".join(str(row[key] or "") for key in ("id", "label", "type", "source_file", "content"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_at(row: Any) -> str:
    value = row["updated_at"] or row["created_at"]
    if value:
        return str(value)
    return datetime.now(timezone.utc).isoformat()


def _metadata_for_memory_vector(row: Any) -> dict[str, str]:
    metadata = _metadata_json(row)
    source_file = str(row["source_file"] or "")
    return {
        "parent_id": str(row["id"]),
        "parent_type": "neuron",
        "brain_lobe": _brain_lobe_from_source(source_file),
        "knowledge_type": str(row["type"] or "fact"),
        "project": _project_from_source(source_file, metadata),
        "source_uri": source_file or f"hive_mind.db:neurons/{row['id']}",
        "hash": _stable_hash(row),
        "valid_at": _valid_at(row),
        "workspace_id": str(row["workspace_id"] or "default"),
    }


def _already_synced(backend: VectorBackend, collection: str, item_id: str, metadata: dict[str, str]) -> bool:
    if not isinstance(backend, MilvusBackend):
        return False
    return backend.count(
        collection,
        filters={
            "id": item_id,
            "hash": metadata["hash"],
            "workspace_id": metadata["workspace_id"],
        },
    ) == 1


def iter_memory_vector_rows(conn, *, limit: int | None = None):
    sql = """
    SELECT
        n.id, n.label, n.type, n.source_file, n.content, n.hash, n.metadata,
        n.created_at, n.updated_at, n.workspace_id,
        sv.embedding
    FROM search_vec sv
    JOIN neurons n ON n.id = sv.neuron_id
    ORDER BY n.id
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    return conn.execute(sql, params)


def sync_memory_vectors_to_milvus(
    conn,
    backend: VectorBackend | None = None,
    *,
    limit: int | None = None,
) -> VectorSyncReport:
    """Backfill/sync live `memory_vectors` from local SQLite to Milvus.

    Idempotency is metadata-hash based: if Milvus already has the same
    `(id, hash, workspace_id)`, the row is skipped; changed hashes are upserted.
    Per-row failures are accumulated in the report so one bad vector does not
    hide the rest of the sync outcome.

    `limit` bounds the read batch for real E2E/smoke runs. The default `None`
    preserves full backfill semantics.
    """
    backend = backend or MilvusBackend()
    report = VectorSyncReport(collection="memory_vectors")

    for row in iter_memory_vector_rows(conn, limit=limit):
        report.scanned += 1
        neuron_id = str(row["id"])
        try:
            vector = _decode_f32(row["embedding"])
            metadata = _metadata_for_memory_vector(row)
            if _already_synced(backend, "memory_vectors", neuron_id, metadata):
                report.skipped += 1
                continue
            backend.upsert("memory_vectors", neuron_id, vector, metadata)
            report.upserted += 1
        except Exception as exc:
            report.failed += 1
            report.errors.append(f"{neuron_id}: {type(exc).__name__}: {exc}")
    return report


def _workspace_from_metadata(raw: str | None) -> str:
    if not raw:
        return "default"
    try:
        data = json.loads(raw)
    except Exception:
        return "default"
    if not isinstance(data, dict):
        return "default"
    return str(data.get("workspace_id") or "default")


def _stable_observation_hash(row: Any) -> str:
    if row["content_hash"]:
        return str(row["content_hash"])
    payload = "|".join(
        str(row[key] or "")
        for key in ("id", "project", "type", "title", "text", "narrative", "facts")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _metadata_for_observation_vector(row: Any) -> dict[str, str]:
    obs_id = str(row["id"])
    return {
        "parent_id": obs_id,
        "parent_type": "claude_mem_observation",
        "brain_lobe": "temporal",
        "knowledge_type": str(row["type"] or "observation"),
        "project": str(row["project"] or "default"),
        "source_uri": f"claude-mem:observations/{obs_id}",
        "hash": _stable_observation_hash(row),
        "valid_at": str(row["created_at"] or datetime.now(timezone.utc).isoformat()),
        "workspace_id": _workspace_from_metadata(row["metadata"]),
    }


def _open_claude_mem_connection(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path).expanduser()
    if not db_path.exists():
        raise FileNotFoundError(f"claude-mem.db nao encontrado: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    try:
        import sqlite_vec

        sqlite_vec.load(conn)
    finally:
        conn.enable_load_extension(False)
    return conn


def iter_observation_vector_rows(conn, *, limit: int | None = None):
    sql = """
    SELECT
        o.id,
        o.project,
        o.text,
        o.type,
        o.title,
        o.facts,
        o.narrative,
        o.created_at,
        o.content_hash,
        o.metadata,
        v.embedding
    FROM vec_observations v
    JOIN observations o ON o.id = v.rowid
    ORDER BY o.id
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    return conn.execute(sql, params)


def sync_observation_vectors_to_milvus(
    claude_mem_db: str | Path,
    backend: VectorBackend | None = None,
    *,
    limit: int | None = None,
) -> VectorSyncReport:
    """Backfill/sync live `observation_vectors` from claude-mem SQLite to Milvus.

    The sqlite-vec-worker remains the canonical writer for `vec_observations`.
    This function only exports already-materialized vectors to Milvus with the
    same `(id, hash, workspace_id)` idempotency contract used by memory vectors.

    `limit` bounds the read batch for real E2E/smoke runs. The default `None`
    preserves full backfill semantics.
    """
    backend = backend or MilvusBackend()
    report = VectorSyncReport(collection="observation_vectors")
    conn = _open_claude_mem_connection(claude_mem_db)
    try:
        for row in iter_observation_vector_rows(conn, limit=limit):
            report.scanned += 1
            obs_key = f"obs-{row['id']}"
            try:
                vector = _decode_f32(row["embedding"])
                metadata = _metadata_for_observation_vector(row)
                if _already_synced(backend, "observation_vectors", obs_key, metadata):
                    report.skipped += 1
                    continue
                backend.upsert("observation_vectors", obs_key, vector, metadata)
                report.upserted += 1
            except Exception as exc:
                report.failed += 1
                report.errors.append(f"{obs_key}: {type(exc).__name__}: {exc}")
    finally:
        conn.close()
    return report


__all__ = [
    "VectorSyncReport",
    "iter_memory_vector_rows",
    "iter_observation_vector_rows",
    "sync_observation_vectors_to_milvus",
    "sync_memory_vectors_to_milvus",
]
