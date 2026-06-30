"""
core/search.py — Busca semântica (HNSW) e full-text (FTS5) para neurônios (F5.2).

Importável por sinapse-mcp.py e testável sem infra MCP. Sem LLM. Sem load_env.
Segue R3/R6 do §14: imports tardios de fastembed/hnswlib, paths via core/paths.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_HNSW_MAX_AGE_DAYS = 7  # índice mais velho que isso → fallback para texto


def project_topic_from_path(source_file: str) -> tuple[str, str]:
    """Extrai (project, topic) do source_file (cortex/temporal/{proj}/{topic}/...)."""
    parts = source_file.replace("\\", "/").split("/")
    try:
        idx = parts.index("temporal")
        proj = parts[idx + 1] if len(parts) > idx + 1 else ""
        topic = parts[idx + 2] if len(parts) > idx + 2 else ""
        return proj, topic
    except (ValueError, IndexError):
        return "", ""


def _parse_meta(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _row_to_result(row, score: Optional[float]) -> dict:
    sf = row["source_file"] or ""
    proj, topic = project_topic_from_path(sf)
    meta = _parse_meta(row["metadata"])
    return {
        "label": row["label"],
        "source_file": sf,
        "project": proj,
        "topic": topic,
        "score": score,
        "aliases": meta.get("aliases", []),
    }


def _text_search(conn, query: str, *, top_k: int, project: Optional[str]) -> list[dict]:
    """FTS5 + LIKE fallback; filtra por project via source_file."""
    like = f"%{query}%"
    q = ("SELECT id, label, type, source_file, metadata "
         "FROM neurons WHERE (label LIKE ? OR content LIKE ?)")
    params: list = [like, like]
    if project:
        q += " AND source_file LIKE ?"
        params.append(f"%/temporal/{project}/%")
    q += f" LIMIT {int(top_k)}"
    rows = conn.execute(q, params).fetchall()
    return [_row_to_result(r, None) for r in rows]


def _hnsw_is_fresh() -> bool:
    """Retorna True se o índice HNSW existir e tiver sido atualizado nos últimos 7 dias."""
    try:
        import core.hnsw_index as hidx
        idx_path = hidx._get_index_path()
        if not idx_path.exists():
            return False
        age_days = (time.time() - idx_path.stat().st_mtime) / 86400
        return age_days <= _HNSW_MAX_AGE_DAYS
    except Exception:
        return False


def _semantic_search(conn, query: str, *, top_k: int,
                     project: Optional[str]) -> Optional[list[dict]]:
    """Busca HNSW cosine. Retorna None se indisponível (sinaliza fallback)."""
    try:
        from core.database import embed_text
        import core.hnsw_index as hidx

        vec = embed_text(query)
        if not hidx.load_or_create():
            return None

        hits = hidx.search(vec, k=top_k * 3)  # over-fetch para filtrar por projeto
        if not hits:
            return None

        neuron_ids = [h["neuron_id"] for h in hits]
        dist_map = {h["neuron_id"]: h["distance"] for h in hits}
        placeholders = ",".join("?" * len(neuron_ids))
        rows = conn.execute(
            f"SELECT id, label, type, source_file, metadata "
            f"FROM neurons WHERE id IN ({placeholders})",
            neuron_ids,
        ).fetchall()

        results: list[dict] = []
        for row in rows:
            nid = row["id"]
            sf = row["source_file"] or ""
            proj, _ = project_topic_from_path(sf)
            if project and proj != project:
                continue
            score = round(1.0 - dist_map.get(nid, 1.0), 4)
            results.append(_row_to_result(row, score))

        # Ordena por score desc; respeita top_k
        results.sort(key=lambda r: r["score"] or 0, reverse=True)
        return results[:top_k]
    except Exception as exc:
        logger.debug("HNSW search failed (%s) — fallback to text", exc)
        return None


def search_neurons(conn, query: str, *, top_k: int = 10,
                   project: Optional[str] = None,
                   mode: str = "semantic") -> list[dict]:
    """Busca neurônios por cosine HNSW (semantic) ou FTS (text).

    mode='semantic': tenta HNSW; cai em text se índice ausente/stale/fastembed indisponível.
    mode='text': full-text direto (label LIKE / content LIKE).
    Retorna [{label, source_file, project, topic, score, aliases}].
    """
    if mode == "semantic" and _hnsw_is_fresh():
        results = _semantic_search(conn, query, top_k=top_k, project=project)
        if results is not None:
            return results
        logger.debug("HNSW semantic unavailable — falling back to full-text")

    return _text_search(conn, query, top_k=top_k, project=project)


def route_retrieval(
    conn,
    query: str,
    *,
    top_k: int = 5,
    project: Optional[str] = None,
    workspace_id: str = "default",
    intent: str | None = None,
) -> dict:
    """K7 adapter: route a query through RetrievalRouter from the search layer.

    `search_neurons` remains the narrow neuron-search API. This adapter is the
    central search-module entrypoint for callers that need the full K7 retrieval
    path, citations, confidence and missing-context contract.
    """
    from core.retrieval.router import route_query

    return route_query(
        query,
        conn=conn,
        top_k=top_k,
        project=project,
        workspace_id=workspace_id,
        intent=intent,  # type: ignore[arg-type]
    )
