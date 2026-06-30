#!/usr/bin/env python3
"""K8 knowledge coverage health.

This complements the existing insula health dashboard. It measures knowledge
coverage across vector collections, detects dirty vector indexes, prunes orphan
vectors with auditable tombstones, and writes a Markdown report under
`cerebro/cortex/insula/saude/`.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import paths as cp  # noqa: E402
from core.database import ensure_migrations, get_connection  # noqa: E402
from core.vector_backend import MilvusBackend, SQLiteVecBackend  # noqa: E402
from core.vector_collections import COLLECTIONS  # noqa: E402


VECTOR_PARENT_SQL: dict[str, str] = {
    "memory_vectors": """
        SELECT sv.neuron_id AS id, 'neuron' AS parent_type, sv.neuron_id AS parent_id
        FROM search_vec sv
        LEFT JOIN neurons n ON n.id = sv.neuron_id
        WHERE n.id IS NULL
    """,
    "document_vectors": """
        SELECT vd.chunk_id AS id, 'document_chunk' AS parent_type, vd.chunk_id AS parent_id
        FROM vec_documents vd
        LEFT JOIN document_chunks dc ON dc.id = vd.chunk_id
        WHERE dc.id IS NULL
    """,
    "visual_vectors": """
        SELECT vv.image_id AS id, 'visual_memory' AS parent_type, vv.image_id AS parent_id
        FROM vec_visual vv
        LEFT JOIN visual_memories vm ON vm.id = vv.image_id
        WHERE vm.id IS NULL
    """,
    "code_vectors": """
        SELECT vc.symbol_id AS id,
               COALESCE(vm.parent_type, 'vector_metadata') AS parent_type,
               COALESCE(vm.parent_id, vc.symbol_id) AS parent_id
        FROM vec_code vc
        LEFT JOIN vector_metadata vm
          ON vm.collection = 'code_vectors' AND vm.id = vc.symbol_id
        LEFT JOIN neurons n
          ON vm.parent_type = 'neuron' AND n.id = vm.parent_id
        WHERE vm.id IS NULL OR (vm.parent_type = 'neuron' AND n.id IS NULL)
    """,
    "graph_vectors": """
        SELECT vg.entity_id AS id,
               COALESCE(vm.parent_type, 'vector_metadata') AS parent_type,
               COALESCE(vm.parent_id, vg.entity_id) AS parent_id
        FROM vec_graph vg
        LEFT JOIN vector_metadata vm
          ON vm.collection = 'graph_vectors' AND vm.id = vg.entity_id
        LEFT JOIN causal_edges ce
          ON vm.parent_type = 'causal_edge' AND ce.id = vm.parent_id
        WHERE vm.id IS NULL OR (vm.parent_type = 'causal_edge' AND ce.id IS NULL)
    """,
    "summary_vectors": """
        SELECT vs.summary_id AS id,
               COALESCE(vm.parent_type, 'vector_metadata') AS parent_type,
               COALESCE(vm.parent_id, vs.summary_id) AS parent_id,
               vm.source_uri AS source_uri
        FROM vec_summary vs
        LEFT JOIN vector_metadata vm
          ON vm.collection = 'summary_vectors' AND vm.id = vs.summary_id
        WHERE vm.id IS NULL
    """,
}


@dataclass
class OrphanVector:
    collection: str
    id: str
    parent_type: str
    parent_id: str
    source_uri: str | None = None


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _count(conn, sql: str, params: tuple[Any, ...] = ()) -> int:
    try:
        return int(conn.execute(sql, params).fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def _pct(part: int | None, total: int | None) -> float | None:
    if total is None or total == 0 or part is None:
        return None
    return round(part * 100.0 / total, 2)


def _summary_files() -> list[Path]:
    roots = [
        cp.CEREBELO / "sessoes",
        cp.CEREBELO / "diario",
        cp.CEREBELO / "semanal",
        cp.CEREBELO / "mensal",
        cp.CEREBELO / "anual",
        cp.CEREBELO / "padroes",
    ]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(sorted(root.rglob("*.md")))
    return files


def _source_total(conn, collection: str, *, quick: bool = False) -> int | None:
    if collection == "memory_vectors":
        return _count(conn, "SELECT COUNT(*) FROM neurons")
    if collection == "document_vectors":
        return _count(conn, "SELECT COUNT(*) FROM document_chunks")
    if collection == "code_vectors":
        return _count(conn, "SELECT COUNT(*) FROM neurons WHERE type = 'code'")
    if collection == "visual_vectors":
        return _count(conn, "SELECT COUNT(*) FROM visual_memories")
    if collection == "graph_vectors":
        return _count(conn, "SELECT COUNT(*) FROM causal_edges")
    if collection == "summary_vectors":
        return len(_summary_files())
    if collection == "observation_vectors":
        if quick:
            return None
        return _claude_mem_observation_total()
    return None


def _vector_count(conn, collection: str, *, quick: bool = False) -> int | None:
    if collection == "observation_vectors":
        if quick:
            return None
        try:
            return SQLiteVecBackend(conn=conn).count(collection)
        except Exception:
            return 0
    c = COLLECTIONS[collection]
    return _count(conn, f"SELECT COUNT(*) FROM {c.table}")


def _claude_mem_observation_total() -> int | None:
    db = Path(
        __import__("os").environ.get(
            "CLAUDE_MEM_DB", str(Path.home() / ".claude-mem" / "claude-mem.db")
        )
    ).expanduser()
    if not db.exists():
        return None
    conn = sqlite3.connect(db)
    try:
        return _count(conn, "SELECT COUNT(*) FROM observations")
    finally:
        conn.close()


def _collection_metrics(conn, *, quick: bool = False) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for collection in COLLECTIONS:
        total = _source_total(conn, collection, quick=quick)
        vectors = _vector_count(conn, collection, quick=quick)
        metrics[collection] = {
            "source_total": total,
            "vector_total": vectors,
            "vectorized_pct": _pct(vectors, total),
        }
    return metrics


def find_orphan_vectors(conn) -> list[OrphanVector]:
    orphans: list[OrphanVector] = []
    for collection, sql in VECTOR_PARENT_SQL.items():
        try:
            for row in conn.execute(sql):
                source_uri = row["source_uri"] if "source_uri" in row.keys() else None
                orphans.append(
                    OrphanVector(
                        collection=collection,
                        id=str(row["id"]),
                        parent_type=str(row["parent_type"] or ""),
                        parent_id=str(row["parent_id"] or ""),
                        source_uri=source_uri,
                    )
                )
        except sqlite3.OperationalError:
            continue
    # Summary vectors can be orphaned by deleted files even when metadata exists.
    try:
        for row in conn.execute(
            """
            SELECT id, parent_type, parent_id, source_uri
            FROM vector_metadata
            WHERE collection = 'summary_vectors'
            """
        ):
            source = str(row["source_uri"] or "")
            if source and not Path(source).exists():
                orphans.append(
                    OrphanVector(
                        collection="summary_vectors",
                        id=str(row["id"]),
                        parent_type=str(row["parent_type"] or "summary_file"),
                        parent_id=str(row["parent_id"] or row["id"]),
                        source_uri=source,
                    )
                )
    except sqlite3.OperationalError:
        pass
    unique: dict[tuple[str, str], OrphanVector] = {}
    for orphan in orphans:
        unique[(orphan.collection, orphan.id)] = orphan
    return list(unique.values())


def _tombstone_id(orphan: OrphanVector, reason: str) -> str:
    key = f"{orphan.collection}:{orphan.id}:{reason}"
    return "tomb-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def forget_vector(
    conn,
    orphan: OrphanVector,
    *,
    reason: str = "orphan_vector",
    actor: str = "knowledge_health",
    workspace_id: str = "default",
) -> str:
    """Remove one vector and write an auditable tombstone."""
    if reason not in {"secret_leak", "expired", "superseded", "user_request", "orphan_vector"}:
        raise ValueError(f"motivo de forget invalido: {reason}")
    c = COLLECTIONS[orphan.collection]
    tomb_id = _tombstone_id(orphan, reason)
    conn.execute(
        """
        INSERT OR REPLACE INTO knowledge_tombstones(
            id, target_type, target_id, collection, reason, actor,
            metadata_json, workspace_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tomb_id,
            "vector",
            orphan.id,
            orphan.collection,
            reason,
            actor,
            json.dumps(asdict(orphan), ensure_ascii=False, sort_keys=True),
            workspace_id,
        ),
    )
    conn.execute(f"DELETE FROM {c.table} WHERE {c.id_col} = ?", (orphan.id,))
    if orphan.collection != "memory_vectors":
        conn.execute(
            "DELETE FROM vector_metadata WHERE collection = ? AND id = ?",
            (orphan.collection, orphan.id),
        )
    conn.commit()
    return tomb_id


def prune_orphan_vectors(conn, *, workspace_id: str = "default") -> list[dict[str, Any]]:
    pruned = []
    for orphan in find_orphan_vectors(conn):
        tombstone_id = forget_vector(conn, orphan, workspace_id=workspace_id)
        data = asdict(orphan)
        data["tombstone_id"] = tombstone_id
        pruned.append(data)
    return pruned


def _observations_linked_pct(conn) -> float | None:
    total = _count(conn, "SELECT COUNT(*) FROM observations WHERE COALESCE(archived, 0) != 2")
    linked = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM observations
        WHERE COALESCE(archived, 0) != 2
          AND (neuron_id IS NOT NULL AND neuron_id != '')
        """,
    )
    return _pct(linked, total)


def _discoveries_pending(conn) -> int:
    pending_candidates = _count(
        conn,
        "SELECT COUNT(*) FROM knowledge_candidates WHERE status = 'candidate'",
    )
    pending_observations = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM observations
        WHERE COALESCE(archived, 0) = 0
          AND LOWER(COALESCE(type, '')) IN ('discovery', 'learning', 'decision')
        """,
    )
    return pending_candidates + pending_observations


def _query_route_distribution(conn) -> dict[str, int]:
    if not _table_exists(conn, "query_route_log"):
        return {}
    rows = conn.execute(
        """
        SELECT COALESCE(first_route, intent, 'unknown') AS route, COUNT(*) AS n
        FROM query_route_log
        WHERE created_at > datetime('now', '-7 days')
        GROUP BY COALESCE(first_route, intent, 'unknown')
        ORDER BY n DESC, route
        """
    ).fetchall()
    return {str(row["route"]): int(row["n"]) for row in rows}


def _milvus_sync_lag(conn, collection_metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    milvus_enabled = (
        os.environ.get("VECTOR_BACKEND", "sqlite_vec").lower() == "milvus"
        or os.environ.get("HIVE_KNOWLEDGE_HEALTH_MILVUS", "").lower() in {"1", "true", "yes", "on"}
    )
    if not milvus_enabled:
        return {"available": False, "reason": "milvus_not_enabled", "total_lag": None}
    try:
        backend = MilvusBackend()
        health = backend.health()
        if not health.get("ok"):
            return {"available": False, "reason": health.get("error") or "unhealthy", "total_lag": None}
        lag_by_collection: dict[str, int] = {}
        total_lag = 0
        for collection, metrics in collection_metrics.items():
            if collection == "observation_vectors":
                local = metrics.get("vector_total") or 0
            elif collection == "memory_vectors":
                local = _vector_count(conn, collection)
            else:
                local = _count(
                    conn,
                    "SELECT COUNT(*) FROM vector_metadata WHERE collection = ?",
                    (collection,),
                )
            remote = backend.count(collection)
            lag = max(0, int(local) - int(remote))
            lag_by_collection[collection] = lag
            total_lag += lag
        return {"available": True, "total_lag": total_lag, "by_collection": lag_by_collection}
    except Exception as exc:
        return {"available": False, "reason": str(exc), "total_lag": None}


def compute_knowledge_health(
    conn,
    *,
    prune_orphans: bool = False,
    workspace_id: str = "default",
    quick: bool = False,
) -> dict[str, Any]:
    ensure_migrations(conn)
    before_orphans = find_orphan_vectors(conn)
    pruned = prune_orphan_vectors(conn, workspace_id=workspace_id) if prune_orphans else []
    after_orphans = find_orphan_vectors(conn)
    collection_metrics = _collection_metrics(conn, quick=quick)
    metrics: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_id": workspace_id,
        "quick": quick,
        "neurons_total": _source_total(conn, "memory_vectors", quick=quick),
        "neurons_vectorized_pct": collection_metrics["memory_vectors"]["vectorized_pct"],
        "observations_linked_pct": _observations_linked_pct(conn),
        "discoveries_pending": _discoveries_pending(conn),
        "summary_vectors_total": collection_metrics["summary_vectors"]["vector_total"],
        "orphan_vectors": len(after_orphans),
        "orphan_vectors_before_prune": len(before_orphans),
        "orphan_vectors_pruned": len(pruned),
        "milvus_sync_lag": _milvus_sync_lag(conn, collection_metrics),
        "query_route_distribution": _query_route_distribution(conn),
        "collections": collection_metrics,
        "orphan_vector_details": [asdict(o) for o in after_orphans],
        "pruned_orphans": pruned,
        "tombstones_total": _count(conn, "SELECT COUNT(*) FROM knowledge_tombstones"),
    }
    for collection, values in collection_metrics.items():
        metrics[f"{collection}_vectorized_pct"] = values["vectorized_pct"]
    metrics["status"] = "ok" if not evaluate_fail_closed(metrics) else "degraded"
    return metrics


def evaluate_fail_closed(metrics: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if metrics.get("orphan_vectors", 0) > 0:
        failures.append(f"orphan_vectors={metrics['orphan_vectors']}")
    document = metrics.get("collections", {}).get("document_vectors", {})
    if (document.get("source_total") or 0) > 0 and document.get("vectorized_pct") is None:
        failures.append("document_vectors_vectorized_pct=n/a")
    if metrics.get("neurons_total", 0) > 0 and metrics.get("neurons_vectorized_pct") is None:
        failures.append("neurons_vectorized_pct=n/a")
    return failures


def render_markdown(metrics: dict[str, Any], failures: list[str]) -> str:
    collections = metrics["collections"]
    rows = "\n".join(
        "| {name} | {source} | {vectors} | {pct} |".format(
            name=name,
            source=data.get("source_total"),
            vectors=data.get("vector_total"),
            pct="n/a" if data.get("vectorized_pct") is None else data.get("vectorized_pct"),
        )
        for name, data in collections.items()
    )
    route_rows = "\n".join(
        f"| {route} | {count} |"
        for route, count in (metrics.get("query_route_distribution") or {}).items()
    ) or "| n/a | 0 |"
    failures_block = "\n".join(f"- {failure}" for failure in failures) or "- nenhum"
    pruned_block = "\n".join(
        f"- `{item['collection']}/{item['id']}` -> `{item['tombstone_id']}`"
        for item in metrics.get("pruned_orphans", [])
    ) or "- nenhum"
    return f"""---
type: knowledge-health
generated_at: {metrics['generated_at']}
workspace_id: {metrics['workspace_id']}
status: {metrics['status']}
---
# Knowledge Health — {metrics['generated_at'][:10]}

<!-- auto:gerado por knowledge_health.py — nao editar a mao -->

## Gates

- Status: `{metrics['status']}`
- Failures: {len(failures)}
- Orphan vectors: {metrics['orphan_vectors']} (antes da poda: {metrics['orphan_vectors_before_prune']})
- Tombstones totais: {metrics['tombstones_total']}

## Metricas Principais

| Metrica | Valor |
|---|---:|
| neurons_total | {metrics['neurons_total']} |
| neurons_vectorized_pct | {metrics['neurons_vectorized_pct']} |
| observations_linked_pct | {metrics['observations_linked_pct']} |
| discoveries_pending | {metrics['discoveries_pending']} |
| summary_vectors_total | {metrics['summary_vectors_total']} |
| orphan_vectors_pruned | {metrics['orphan_vectors_pruned']} |
| milvus_sync_lag.total_lag | {metrics['milvus_sync_lag'].get('total_lag')} |

## Cobertura Por Colecao

| Colecao | Fonte | Vetores | Vectorized % |
|---|---:|---:|---:|
{rows}

## Distribuicao De Rotas

| Rota | Consultas 7d |
|---|---:|
{route_rows}

## Orfaos Podados

{pruned_block}

## Falhas Fail-Closed

{failures_block}
"""


def write_report(metrics: dict[str, Any], failures: list[str], *, root: Path = cp.SAUDE_ROOT) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    dest = root / f"knowledge-health-{date}.md"
    dest.write_text(render_markdown(metrics, failures), encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="K8 knowledge coverage health")
    parser.add_argument("--fail-closed", action="store_true", help="exit 1 when hard K8 gates fail")
    parser.add_argument("--no-prune", action="store_true", help="measure only; do not prune orphan vectors")
    parser.add_argument("--no-report", action="store_true", help="do not write Markdown report")
    parser.add_argument("--json", action="store_true", help="print compact JSON")
    parser.add_argument("--workspace-id", default="default")
    args = parser.parse_args(argv)

    conn = get_connection()
    try:
        metrics = compute_knowledge_health(
            conn,
            prune_orphans=not args.no_prune,
            workspace_id=args.workspace_id,
        )
        failures = evaluate_fail_closed(metrics)
        report_path = None if args.no_report else write_report(metrics, failures)
        payload = {"metrics": metrics, "failures": failures, "report_path": str(report_path) if report_path else None}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        if args.fail_closed and failures:
            return 1
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
