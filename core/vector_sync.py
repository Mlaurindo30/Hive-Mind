"""Vector sync/backfill helpers for K2.

Live sync paths:
- `memory_vectors`: local `hive_mind.db/search_vec` -> Milvus.
- `observation_vectors`: global/local `claude-mem.db/vec_observations` -> Milvus.

Auxiliary collection sync paths:
- `document_vectors`: document neurons with existing search_vec embeddings.
- `code_vectors`: code neurons with existing search_vec embeddings.
- `visual_vectors`: visual_memories embedded from description/OCR/path.
- `graph_vectors`: causal_edges embedded from edge text.
- `summary_vectors`: cerebelo summary/session markdown files embedded from text.
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
from core.vector_collections import COLLECTIONS, EMBED_DIM, get_collection


AUXILIARY_COLLECTIONS = (
    "document_vectors",
    "code_vectors",
    "visual_vectors",
    "graph_vectors",
    "summary_vectors",
)
BATCH_SIZE = 256


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


def _flush_sync_batch(
    backend: VectorBackend,
    collection: str,
    rows: list[dict[str, Any]],
    report: VectorSyncReport,
) -> None:
    if not rows:
        return
    try:
        if isinstance(backend, MilvusBackend):
            existing = backend.existing_hashes(collection, [str(row["id"]) for row in rows])
            pending = []
            for row in rows:
                key = (str(row["id"]), str(row["workspace_id"]))
                if existing.get(key) == str(row["hash"]):
                    report.skipped += 1
                else:
                    pending.append(row)
            backend.upsert_many(collection, pending)
            report.upserted += len(pending)
            return

        for row in rows:
            if _already_synced(backend, collection, str(row["id"]), row):
                report.skipped += 1
                continue
            backend.upsert(collection, str(row["id"]), row["vector"], row)
            report.upserted += 1
    except Exception as exc:
        report.failed += len(rows)
        sample = ", ".join(str(row.get("id")) for row in rows[:5])
        report.errors.append(f"{sample}: {type(exc).__name__}: {exc}")


def _queue_sync_row(
    backend: VectorBackend,
    collection: str,
    batch: list[dict[str, Any]],
    report: VectorSyncReport,
    *,
    item_id: str,
    vector: list[float],
    metadata: dict[str, str],
) -> None:
    batch.append({"id": item_id, "vector": vector, **metadata})
    if len(batch) >= BATCH_SIZE:
        _flush_sync_batch(backend, collection, batch, report)
        batch.clear()


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
    batch: list[dict[str, Any]] = []

    for row in iter_memory_vector_rows(conn, limit=limit):
        report.scanned += 1
        neuron_id = str(row["id"])
        try:
            vector = _decode_f32(row["embedding"])
            metadata = _metadata_for_memory_vector(row)
            _queue_sync_row(
                backend,
                "memory_vectors",
                batch,
                report,
                item_id=neuron_id,
                vector=vector,
                metadata=metadata,
            )
        except Exception as exc:
            report.failed += 1
            report.errors.append(f"{neuron_id}: {type(exc).__name__}: {exc}")
    _flush_sync_batch(backend, "memory_vectors", batch, report)
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


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def _upsert_sqlite_vector(conn, collection: str, item_id: str, vector: list[float], metadata: dict[str, str]) -> None:
    from core.database import serialize_f32

    c = get_collection(collection)
    conn.execute(f"DELETE FROM {c.table} WHERE {c.id_col} = ?", (item_id,))
    conn.execute(
        f"INSERT INTO {c.table}({c.id_col}, embedding) VALUES (?, ?)",
        (item_id, serialize_f32(vector)),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO vector_metadata(
            collection, id, parent_id, parent_type, brain_lobe, knowledge_type,
            project, source_uri, hash, valid_at, workspace_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            collection,
            item_id,
            metadata["parent_id"],
            metadata["parent_type"],
            metadata["brain_lobe"],
            metadata["knowledge_type"],
            metadata["project"],
            metadata["source_uri"],
            metadata["hash"],
            metadata["valid_at"],
            metadata["workspace_id"],
        ),
    )


def _metadata_for_neuron_collection(row: Any, collection: str, knowledge_type: str) -> dict[str, str]:
    base = _metadata_for_memory_vector(row)
    base["parent_type"] = "neuron"
    base["knowledge_type"] = knowledge_type
    if collection == "document_vectors":
        base["brain_lobe"] = "parietal"
    elif collection == "code_vectors":
        base["brain_lobe"] = "occipital"
    return base


def _iter_neuron_type_vectors(conn, neuron_type: str, *, limit: int | None = None):
    sql = """
    SELECT
        n.id, n.label, n.type, n.source_file, n.content, n.hash, n.metadata,
        n.created_at, n.updated_at, n.workspace_id,
        sv.embedding
    FROM neurons n
    JOIN search_vec sv ON sv.neuron_id = n.id
    WHERE n.type = ?
    ORDER BY n.id
    """
    params: tuple[Any, ...] = (neuron_type,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (neuron_type, int(limit))
    return conn.execute(sql, params)


def _embedding_for_text(text: str) -> list[float]:
    from core.database import embed_text

    return embed_text(text[:5000])


def _backfill_neuron_collection(conn, collection: str, neuron_type: str, *, limit: int | None = None) -> VectorSyncReport:
    report = VectorSyncReport(collection=collection)
    rows = list(_iter_neuron_type_vectors(conn, neuron_type, limit=limit))
    for row in rows:
        report.scanned += 1
        item_id = str(row["id"])
        try:
            metadata = _metadata_for_neuron_collection(row, collection, neuron_type)
            _upsert_sqlite_vector(conn, collection, item_id, _decode_f32(row["embedding"]), metadata)
            report.upserted += 1
        except Exception as exc:
            report.failed += 1
            report.errors.append(f"{item_id}: {type(exc).__name__}: {exc}")
    return report


def _backfill_visual_vectors(conn, *, limit: int | None = None) -> VectorSyncReport:
    report = VectorSyncReport(collection="visual_vectors")
    sql = """
    SELECT id, image_path, description, ocr_text, neuron_id, metadata, created_at, workspace_id
    FROM visual_memories
    ORDER BY id
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    rows = list(conn.execute(sql, params))
    for row in rows:
        report.scanned += 1
        item_id = str(row["id"])
        text = "\n".join(str(row[key] or "") for key in ("image_path", "description", "ocr_text"))
        try:
            metadata = {
                "parent_id": str(row["neuron_id"] or item_id),
                "parent_type": "visual_memory",
                "brain_lobe": "occipital",
                "knowledge_type": "visual",
                "project": "default",
                "source_uri": str(row["image_path"] or f"hive_mind.db:visual_memories/{item_id}"),
                "hash": _sha256(text),
                "valid_at": str(row["created_at"] or datetime.now(timezone.utc).isoformat()),
                "workspace_id": str(row["workspace_id"] or "default"),
            }
            _upsert_sqlite_vector(conn, "visual_vectors", item_id, _embedding_for_text(text), metadata)
            report.upserted += 1
        except Exception as exc:
            report.failed += 1
            report.errors.append(f"{item_id}: {type(exc).__name__}: {exc}")
    return report


def _backfill_graph_vectors(conn, *, limit: int | None = None) -> VectorSyncReport:
    report = VectorSyncReport(collection="graph_vectors")
    sql = """
    SELECT id, cause_neuron_id, effect_neuron_id, label, confidence, source, created_at
    FROM causal_edges
    ORDER BY id
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    rows = list(conn.execute(sql, params))
    for row in rows:
        report.scanned += 1
        item_id = str(row["id"])
        text = f"{row['cause_neuron_id']} {row['label'] or 'relates_to'} {row['effect_neuron_id']} source={row['source'] or ''}"
        try:
            metadata = {
                "parent_id": item_id,
                "parent_type": "causal_edge",
                "brain_lobe": "temporal",
                "knowledge_type": "graph_edge",
                "project": "default",
                "source_uri": f"hive_mind.db:causal_edges/{item_id}",
                "hash": _sha256(text),
                "valid_at": str(row["created_at"] or datetime.now(timezone.utc).isoformat()),
                "workspace_id": "default",
            }
            _upsert_sqlite_vector(conn, "graph_vectors", item_id, _embedding_for_text(text), metadata)
            report.upserted += 1
        except Exception as exc:
            report.failed += 1
            report.errors.append(f"{item_id}: {type(exc).__name__}: {exc}")
    return report


def _summary_files(summary_roots: list[Path] | None = None) -> list[Path]:
    if summary_roots is None:
        from core.paths import CEREBELO

        summary_roots = [
            CEREBELO / "sessoes",
            CEREBELO / "diario",
            CEREBELO / "semanal",
            CEREBELO / "mensal",
            CEREBELO / "anual",
            CEREBELO / "padroes",
        ]
    files: list[Path] = []
    for root in summary_roots:
        root = Path(root)
        if root.exists():
            files.extend(sorted(root.rglob("*.md")))
    return files


def _backfill_summary_vectors(conn, *, summary_roots: list[Path] | None = None, limit: int | None = None) -> VectorSyncReport:
    report = VectorSyncReport(collection="summary_vectors")
    files = _summary_files(summary_roots)
    if limit is not None:
        files = files[: int(limit)]
    for path in files:
        item_id = _sha256(str(path))[:32]
        report.scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            metadata = {
                "parent_id": item_id,
                "parent_type": "summary_file",
                "brain_lobe": "cerebelo",
                "knowledge_type": "summary",
                "project": "default",
                "source_uri": str(path),
                "hash": _sha256(text),
                "valid_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                "workspace_id": "default",
            }
            _upsert_sqlite_vector(conn, "summary_vectors", item_id, _embedding_for_text(text), metadata)
            report.upserted += 1
        except Exception as exc:
            report.failed += 1
            report.errors.append(f"{item_id}: {type(exc).__name__}: {exc}")
    return report


def index_summary_file_to_sqlite(
    conn,
    path: Path,
    *,
    cadence: str,
    workspace_id: str = "default",
) -> str:
    """Embed one cadence summary markdown file into `summary_vectors`.

    Used by K5 writers immediately after writing monthly/yearly summaries so the
    vector layer is populated without waiting for a later backfill.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    item_id = _sha256(str(path))[:32]
    metadata = {
        "parent_id": item_id,
        "parent_type": "summary_file",
        "brain_lobe": "cerebelo",
        "knowledge_type": f"{cadence}_summary",
        "project": "default",
        "source_uri": str(path),
        "hash": _sha256(text),
        "valid_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "workspace_id": workspace_id,
    }
    _upsert_sqlite_vector(conn, "summary_vectors", item_id, _embedding_for_text(text), metadata)
    conn.commit()
    return item_id


def backfill_auxiliary_vectors_to_sqlite(
    conn,
    *,
    summary_roots: list[Path] | None = None,
    limit: int | None = None,
) -> list[VectorSyncReport]:
    """Backfill K2 auxiliary sqlite-vec collections from real local sources."""
    reports = [
        _backfill_neuron_collection(conn, "document_vectors", "document", limit=limit),
        _backfill_neuron_collection(conn, "code_vectors", "code", limit=limit),
        _backfill_visual_vectors(conn, limit=limit),
        _backfill_graph_vectors(conn, limit=limit),
        _backfill_summary_vectors(conn, summary_roots=summary_roots, limit=limit),
    ]
    conn.commit()
    return reports


def _iter_vector_metadata_rows(conn, collection: str, *, limit: int | None = None):
    c = get_collection(collection)
    sql = f"""
    SELECT
        vm.*,
        v.embedding
    FROM vector_metadata vm
    JOIN {c.table} v ON v.{c.id_col} = vm.id
    WHERE vm.collection = ?
    ORDER BY vm.id
    """
    params: tuple[Any, ...] = (collection,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (collection, int(limit))
    return conn.execute(sql, params)


def sync_auxiliary_vectors_to_milvus(
    conn,
    backend: VectorBackend | None = None,
    *,
    collections: tuple[str, ...] = AUXILIARY_COLLECTIONS,
    limit: int | None = None,
) -> list[VectorSyncReport]:
    """Sync auxiliary K2 collections from local sqlite-vec tables to Milvus."""
    backend = backend or MilvusBackend()
    reports: list[VectorSyncReport] = []
    for collection in collections:
        if collection not in AUXILIARY_COLLECTIONS:
            raise ValueError(f"colecao auxiliar K2 desconhecida: {collection}")
        report = VectorSyncReport(collection=collection)
        batch: list[dict[str, Any]] = []
        for row in _iter_vector_metadata_rows(conn, collection, limit=limit):
            report.scanned += 1
            item_id = str(row["id"])
            try:
                metadata = {
                    field: str(row[field])
                    for field in MilvusBackend.METADATA_FIELDS
                }
                vector = _decode_f32(row["embedding"])
                _queue_sync_row(
                    backend,
                    collection,
                    batch,
                    report,
                    item_id=item_id,
                    vector=vector,
                    metadata=metadata,
                )
            except Exception as exc:
                report.failed += 1
                report.errors.append(f"{item_id}: {type(exc).__name__}: {exc}")
        _flush_sync_batch(backend, collection, batch, report)
        reports.append(report)
    return reports


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
    batch: list[dict[str, Any]] = []
    try:
        for row in iter_observation_vector_rows(conn, limit=limit):
            report.scanned += 1
            obs_key = f"obs-{row['id']}"
            try:
                vector = _decode_f32(row["embedding"])
                metadata = _metadata_for_observation_vector(row)
                _queue_sync_row(
                    backend,
                    "observation_vectors",
                    batch,
                    report,
                    item_id=obs_key,
                    vector=vector,
                    metadata=metadata,
                )
            except Exception as exc:
                report.failed += 1
                report.errors.append(f"{obs_key}: {type(exc).__name__}: {exc}")
        _flush_sync_batch(backend, "observation_vectors", batch, report)
    finally:
        conn.close()
    return report


__all__ = [
    "AUXILIARY_COLLECTIONS",
    "VectorSyncReport",
    "backfill_auxiliary_vectors_to_sqlite",
    "iter_memory_vector_rows",
    "iter_observation_vector_rows",
    "sync_auxiliary_vectors_to_milvus",
    "sync_observation_vectors_to_milvus",
    "sync_memory_vectors_to_milvus",
]
