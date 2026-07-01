"""K7 RetrievalRouter.

Routes a user query to the best brain lobe/backend while preserving the legacy
`sinapse_query` Context Fusion contract. The router is intentionally local-first:
specific routes fail open into the hybrid context-fusion route and every step is
reported in `retrieval_path`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterable, Literal
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from core.database import embed_text, get_connection
from core.vector_backend import SQLiteVecBackend, get_vector_backend


Intent = Literal[
    "recent_activity",
    "decision",
    "learning",
    "document",
    "code",
    "causal",
    "multi_hop",
    "visual",
    "self_state",
    "operational",
    "sector",
    "hybrid",
]

INTENTS: tuple[Intent, ...] = (
    "recent_activity",
    "decision",
    "learning",
    "document",
    "code",
    "causal",
    "multi_hop",
    "visual",
    "self_state",
    "operational",
    "sector",
    "hybrid",
)


@dataclass
class RouteStep:
    route: str
    backend: str
    status: str
    elapsed_ms: float
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "backend": self.backend,
            "status": self.status,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "details": self.details,
        }


class IntentDecision(BaseModel):
    intent: str = Field(description=f"One of: {', '.join(INTENTS)}")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class RetrievalRouter:
    """Route queries across temporal, vector, graph and hybrid retrieval."""

    def __init__(
        self,
        *,
        conn=None,
        workspace_id: str = "default",
        project: str | None = None,
        sinapse_query_fn: Callable[[str], dict | None] | None = None,
        claude_mem_url: str | None = None,
    ):
        self.conn = conn or get_connection()
        self._owns_conn = conn is None
        _ensure_route_log_schema(self.conn)
        self.workspace_id = workspace_id
        self.project = project
        self.sinapse_query_fn = sinapse_query_fn
        self.claude_mem_url = (claude_mem_url or os.environ.get("CLAUDE_MEM_URL") or "http://127.0.0.1:37700").rstrip("/")
        # Explicit connections are usually scoped DBs (tests, maintenance,
        # route_retrieval(conn=...)); querying global Milvus would mix states.
        self.vector_backend = SQLiteVecBackend(conn=self.conn) if conn is not None else get_vector_backend(conn=self.conn)

    def close(self) -> None:
        if self._owns_conn:
            self.conn.close()

    def route(self, query: str, *, top_k: int = 5, intent: Intent | None = None) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            return self._empty("hybrid", query, ["query vazia"])

        decision = self.classify(query, explicit_intent=intent)
        missing_context: list[str] = []
        path: list[RouteStep] = []
        citations: list[dict[str, Any]] = []
        answer_context: list[dict[str, Any]] = []

        route_order = self._route_order(decision.intent)
        for route_name in route_order:
            route_result = self._run_route(route_name, query, top_k=top_k)
            path.extend(route_result["path"])
            citations.extend(route_result["citations"])
            answer_context.extend(route_result["answer_context"])
            missing_context.extend(route_result["missing_context"])
            if route_result["answer_context"] and route_name != "hybrid":
                break

        if not answer_context and "hybrid" not in route_order:
            route_result = self._run_route("hybrid", query, top_k=top_k)
            path.extend(route_result["path"])
            citations.extend(route_result["citations"])
            answer_context.extend(route_result["answer_context"])
            missing_context.extend(route_result["missing_context"])

        answer_context = _dedupe_context(answer_context)[:top_k]
        citations = _dedupe_citations(citations)[:top_k]
        if _reranker_enabled():
            ranked = _rerank(query, answer_context, path)
            answer_context = ranked[:top_k]
            keep_ids = {item.get("id") or item.get("source_uri") for item in answer_context}
            citations = [
                c for c in citations
                if (c.get("id") or c.get("source_uri") or c.get("parent_id")) in keep_ids
            ] or citations[:top_k]

        confidence = self._confidence(decision.confidence, answer_context, path, missing_context)
        result = {
            "source": "retrieval-router",
            "query": query,
            "intent": decision.intent,
            "intent_confidence": decision.confidence,
            "intent_reason": decision.reason,
            "answer_context": answer_context,
            "citations": citations,
            "retrieval_path": [step.as_dict() for step in path],
            "confidence": confidence,
            "missing_context": sorted(set(missing_context)),
        }
        result.update(_legacy_projection(answer_context))
        self._log_route(query, result)
        return result

    def classify(self, query: str, *, explicit_intent: Intent | None = None) -> IntentDecision:
        if explicit_intent in INTENTS:
            return IntentDecision(intent=explicit_intent, confidence=1.0, reason="explicit")

        llm_decision = self._classify_with_topic_router(query)
        if llm_decision is not None and llm_decision.intent in INTENTS:
            return llm_decision

        return _classify_heuristic(query)

    def _classify_with_topic_router(self, query: str) -> IntentDecision | None:
        if os.environ.get("HIVE_RETRIEVAL_LLM_INTENT", "0") not in {"1", "true", "yes", "on"}:
            return None
        try:
            from core.auth import load_env, get_role_config
            from core.llm_client import call_llm_structured

            load_env()
            cfg = get_role_config("topic_router")
            if not cfg:
                return None
            prompt = (
                "Classifique a consulta em uma intent do RetrievalRouter. "
                f"Intents validas: {', '.join(INTENTS)}.\nConsulta: {query}"
            )
            out = call_llm_structured(
                prompt,
                "Responda apenas JSON valido no schema.",
                IntentDecision,
                provider=cfg["provider"],
                model=cfg["model"],
            )
            if out.intent not in INTENTS:
                return None
            return out
        except Exception:
            return None

    def _route_order(self, intent: str) -> list[Intent]:
        routes: dict[str, list[Intent]] = {
            "recent_activity": ["recent_activity", "hybrid"],
            "decision": ["decision", "hybrid"],
            "learning": ["learning", "hybrid"],
            "document": ["document", "hybrid"],
            "code": ["code", "hybrid"],
            "causal": ["causal", "hybrid"],
            "multi_hop": ["multi_hop", "hybrid"],
            "visual": ["visual", "hybrid"],
            "self_state": ["self_state", "hybrid"],
            "operational": ["operational", "hybrid"],
            "sector": ["sector", "hybrid"],
            "hybrid": ["hybrid"],
        }
        return routes.get(intent, ["hybrid"])

    def _run_route(self, route_name: str, query: str, *, top_k: int) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            if route_name == "recent_activity":
                data = self._route_temporal(query, top_k=top_k)
            elif route_name == "document":
                data = self._route_vector("document_vectors", query, top_k=top_k)
            elif route_name == "code":
                data = self._route_code(query, top_k=top_k)
            elif route_name == "visual":
                data = self._route_vector("visual_vectors", query, top_k=top_k)
            elif route_name in {"decision", "learning", "operational", "self_state", "sector"}:
                data = self._route_memory(query, route_name, top_k=top_k)
            elif route_name == "causal":
                data = self._route_causal(query, top_k=top_k)
            elif route_name == "multi_hop":
                data = self._route_lightrag(query, top_k=top_k)
            else:
                data = self._route_hybrid(query, top_k=top_k)
            status = "hit" if data["answer_context"] else "miss"
            if not data["answer_context"]:
                data["missing_context"].append(f"{route_name}:sem_resultado")
            data["path"].insert(0, RouteStep(route_name, data["backend"], status, (time.perf_counter() - start) * 1000.0, data.get("details", {})))
            return data
        except Exception as exc:
            return {
                "backend": route_name,
                "answer_context": [],
                "citations": [],
                "missing_context": [f"{route_name}:{type(exc).__name__}:{str(exc)[:120]}"],
                "path": [RouteStep(route_name, route_name, "error", (time.perf_counter() - start) * 1000.0, {"error": str(exc)[:240]})],
            }

    def _route_temporal(self, query: str, *, top_k: int) -> dict[str, Any]:
        search = self._claude_mem_get("/api/search", {"query": query, "limit": top_k, "project": self.project})
        ids = _extract_observation_ids(search)
        hydrated = None
        if ids:
            hydrated = self._claude_mem_post("/api/observations/batch", {"ids": ids[:top_k], "project": self.project})
        context = _temporal_context(search, hydrated)
        return {
            "backend": "claude-mem temporal",
            "answer_context": context,
            "citations": [_citation_from_context(item) for item in context],
            "missing_context": [],
            "path": [],
            "details": {"ids": ids[:top_k], "hydrated": bool(hydrated)},
        }

    def _route_memory(self, query: str, intent: str, *, top_k: int) -> dict[str, Any]:
        type_map = {
            "decision": {"decision", "preference"},
            "learning": {"learning", "pattern"},
            "operational": {"operational_fact", "rationale"},
            "self_state": {"summary", "project_status", "health"},
            "sector": {"sector", "lore"},
        }
        hits = self._query_vector_collection("memory_vectors", query, top_k=top_k * 3)
        rows = self._hydrate_neurons([str(hit["id"]) for hit in hits])
        allowed = type_map.get(intent)
        context: list[dict[str, Any]] = []
        for hit in hits:
            row = rows.get(str(hit["id"]))
            if not row:
                continue
            if allowed and str(row["type"] or "") not in allowed:
                # Keep sector/self_state useful even when type is generic but path matches lobe.
                source_file = str(row["source_file"] or "")
                if intent == "sector" and "/diencefalo/" not in source_file:
                    continue
                if intent == "self_state" and "/insula/" not in source_file and "/brain/" not in source_file:
                    continue
                if intent not in {"sector", "self_state"}:
                    continue
            context.append(_neuron_context(row, score=hit.get("score"), route=intent))
            if len(context) >= top_k:
                break
        return {
            "backend": "memory_vectors",
            "answer_context": context,
            "citations": [_citation_from_context(item) for item in context],
            "missing_context": [],
            "path": [],
            "details": {"collection": "memory_vectors"},
        }

    def _route_vector(self, collection: str, query: str, *, top_k: int) -> dict[str, Any]:
        hits = self._query_vector_collection(collection, query, top_k=top_k)
        context = [self._hydrate_vector_hit(collection, hit) for hit in hits]
        context = [item for item in context if item]
        return {
            "backend": collection,
            "answer_context": context,
            "citations": [_citation_from_context(item) for item in context],
            "missing_context": [],
            "path": [],
            "details": {"collection": collection},
        }

    def _route_code(self, query: str, *, top_k: int) -> dict[str, Any]:
        vector_data = self._route_vector("code_vectors", query, top_k=top_k)
        graph_data = self._route_graphify(query, top_k=top_k)
        return {
            "backend": "code_vectors+graphify",
            "answer_context": [*vector_data["answer_context"], *graph_data["answer_context"]][:top_k],
            "citations": [*vector_data["citations"], *graph_data["citations"]][:top_k],
            "missing_context": [*vector_data["missing_context"], *graph_data["missing_context"]],
            "path": [*vector_data["path"], *graph_data["path"]],
            "details": {"collections": ["code_vectors"], "graphify": True},
        }

    def _route_graphify(self, query: str, *, top_k: int) -> dict[str, Any]:
        from core import paths as cp
        from core.memory.backends.graphify import backend_graphify

        graph_path = str(cp.OCCIPITAL / "grafo" / "graph.json")
        result = backend_graphify(query, graph_path, {}, [0.0], 0, top_k)
        context: list[dict[str, Any]] = []
        if result:
            for node in result.get("nodes", []):
                context.append({
                    "id": node.get("source") or node.get("label"),
                    "type": "graphify_node",
                    "title": node.get("label") or "",
                    "content": node.get("type") or "",
                    "source_uri": node.get("source") or "graphify:graph.json",
                    "score": node.get("score"),
                    "route": "graphify",
                })
        return {
            "backend": "graphify",
            "answer_context": context[:top_k],
            "citations": [_citation_from_context(item) for item in context[:top_k]],
            "missing_context": [],
            "path": [],
            "details": {"graph_json": graph_path},
        }

    def _route_causal(self, query: str, *, top_k: int) -> dict[str, Any]:
        context: list[dict[str, Any]] = []
        try:
            from integrations.graphiti import graphiti_available, search_graph

            if graphiti_available():
                for item in search_graph(query, num_results=top_k):
                    context.append({
                        "id": item.get("uuid") or item.get("name") or item.get("source") or item.get("target"),
                        "type": "graphiti_fact",
                        "title": item.get("name") or item.get("fact") or "Graphiti result",
                        "content": item.get("fact") or item.get("summary") or json.dumps(item, ensure_ascii=False),
                        "source_uri": "graphiti:falkordb",
                        "score": item.get("score"),
                        "route": "causal",
                    })
        except Exception:
            context = []
        graph_vectors = self._route_vector("graph_vectors", query, top_k=top_k)
        return {
            "backend": "graphiti+graph_vectors",
            "answer_context": [*context, *graph_vectors["answer_context"]][:top_k],
            "citations": [_citation_from_context(item) for item in [*context, *graph_vectors["answer_context"]]][:top_k],
            "missing_context": graph_vectors["missing_context"],
            "path": graph_vectors["path"],
            "details": {"graphiti": True, "collection": "graph_vectors"},
        }

    def _route_lightrag(self, query: str, *, top_k: int) -> dict[str, Any]:
        context: list[dict[str, Any]] = []
        try:
            from core.lightrag_index import query_rag_sync

            text = query_rag_sync(query, mode="hybrid")
            if text:
                context.append({
                    "id": "lightrag:hybrid",
                    "type": "lightrag_context",
                    "title": "LightRAG hybrid context",
                    "content": text,
                    "source_uri": "lightrag:claude-mem/data/lightrag",
                    "score": 1.0,
                    "route": "multi_hop",
                })
        except Exception:
            context = []
        if not context:
            graph_vectors = self._route_vector("graph_vectors", query, top_k=top_k)
            context = graph_vectors["answer_context"]
        return {
            "backend": "lightrag",
            "answer_context": context[:top_k],
            "citations": [_citation_from_context(item) for item in context[:top_k]],
            "missing_context": [],
            "path": [],
            "details": {"mode": "hybrid"},
        }

    def _route_hybrid(self, query: str, *, top_k: int) -> dict[str, Any]:
        result = self.sinapse_query_fn(query) if self.sinapse_query_fn else None
        context = _context_from_legacy_result(result, top_k=top_k) if result else []
        return {
            "backend": "sinapse_query/context_fusion",
            "answer_context": context,
            "citations": [_citation_from_context(item) for item in context],
            "missing_context": [] if result else ["hybrid:context_fusion_indisponivel"],
            "path": [],
            "details": {"source": result.get("source") if isinstance(result, dict) else None},
            "legacy_result": result,
        }

    def _query_vector_collection(self, collection: str, query: str, *, top_k: int) -> list[dict[str, Any]]:
        filters = {"workspace_id": self.workspace_id}
        if self.project and collection != "memory_vectors":
            filters["project"] = self.project
        return self.vector_backend.query(collection, embed_text(query), top_k=top_k, filters=filters)

    def _hydrate_neurons(self, ids: Iterable[str]) -> dict[str, Any]:
        ids = [str(i) for i in ids if i]
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        rows = self.conn.execute(f"SELECT * FROM neurons WHERE id IN ({placeholders})", ids).fetchall()
        return {str(row["id"]): row for row in rows}

    def _hydrate_vector_hit(self, collection: str, hit: dict[str, Any]) -> dict[str, Any] | None:
        item_id = str(hit["id"])
        if collection == "document_vectors":
            row = self.conn.execute("SELECT * FROM document_chunks WHERE id = ?", (item_id,)).fetchone()
            if not row:
                return _metadata_context(collection, hit)
            return {
                "id": row["id"],
                "type": "document_chunk",
                "title": row["heading"] or Path(row["source_uri"]).name,
                "content": row["content"],
                "source_uri": row["source_uri"],
                "offset_start": row["offset_start"],
                "offset_end": row["offset_end"],
                "parent_id": row["parent_id"],
                "score": hit.get("score"),
                "route": "document",
            }
        if collection == "visual_vectors":
            row = self.conn.execute("SELECT * FROM visual_memories WHERE id = ?", (item_id,)).fetchone()
            if row:
                return {
                    "id": row["id"],
                    "type": "visual_memory",
                    "title": Path(row["image_path"]).name if row["image_path"] else row["id"],
                    "content": "\n".join(str(row[key] or "") for key in ("description", "ocr_text")),
                    "source_uri": row["image_path"],
                    "parent_id": row["neuron_id"] or row["id"],
                    "score": hit.get("score"),
                    "route": "visual",
                }
        if collection in {"code_vectors", "graph_vectors", "summary_vectors"}:
            return _metadata_context(collection, hit)
        return None

    def _claude_mem_get(self, path: str, params: dict[str, Any], timeout: int = 5) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v not in (None, "", [])}
        suffix = f"?{urlencode(clean)}" if clean else ""
        req = Request(f"{self.claude_mem_url}{path}{suffix}", method="GET")
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (URLError, OSError, json.JSONDecodeError):
            return {}

    def _claude_mem_post(self, path: str, payload: dict[str, Any], timeout: int = 5) -> dict[str, Any]:
        clean = {k: v for k, v in payload.items() if v not in (None, "", [])}
        req = Request(
            f"{self.claude_mem_url}{path}",
            method="POST",
            data=json.dumps(clean).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (URLError, OSError, json.JSONDecodeError):
            return {}

    def _confidence(
        self,
        intent_confidence: float,
        answer_context: list[dict[str, Any]],
        path: list[RouteStep],
        missing_context: list[str],
    ) -> float:
        if not answer_context:
            return 0.0
        hit_steps = sum(1 for step in path if step.status == "hit")
        base = min(1.0, 0.35 + 0.15 * len(answer_context) + 0.1 * hit_steps)
        penalty = min(0.4, 0.08 * len(set(missing_context)))
        return round(max(0.0, min(1.0, base * (0.6 + 0.4 * intent_confidence) - penalty)), 3)

    def _empty(self, intent: Intent, query: str, missing: list[str]) -> dict[str, Any]:
        return {
            "source": "retrieval-router",
            "query": query,
            "intent": intent,
            "intent_confidence": 0.0,
            "intent_reason": "empty",
            "answer_context": [],
            "citations": [],
            "retrieval_path": [],
            "confidence": 0.0,
            "missing_context": missing,
            "observations": [],
            "nodes": [],
            "edges": [],
        }

    def _log_route(self, query: str, result: dict[str, Any]) -> None:
        try:
            path = result.get("retrieval_path") or []
            first_route = path[0].get("route") if path else None
            self.conn.execute("PRAGMA busy_timeout = 250")
            self.conn.execute(
                """
                INSERT INTO query_route_log(
                    query_hash, intent, first_route, retrieval_path_json,
                    confidence, workspace_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    hashlib.sha256(query.encode("utf-8", "ignore")).hexdigest(),
                    str(result.get("intent") or "hybrid"),
                    first_route,
                    json.dumps(path, ensure_ascii=False),
                    float(result.get("confidence") or 0.0),
                    self.workspace_id,
                ),
            )
            self.conn.commit()
        except Exception:
            pass


def route_query(
    query: str,
    *,
    top_k: int = 5,
    intent: Intent | None = None,
    conn=None,
    project: str | None = None,
    workspace_id: str = "default",
    sinapse_query_fn: Callable[[str], dict | None] | None = None,
) -> dict[str, Any]:
    router = RetrievalRouter(
        conn=conn,
        project=project,
        workspace_id=workspace_id,
        sinapse_query_fn=sinapse_query_fn,
    )
    try:
        return router.route(query, top_k=top_k, intent=intent)
    finally:
        router.close()


def _ensure_route_log_schema(conn) -> None:
    """Keep per-query route telemetry cheap.

    Full UMC migrations are owned by `core.database.ensure_migrations`. The
    router only needs the append-only K8 route log before it can serve a query,
    so doing the full migration stack in every CLI/API request makes short
    queries timeout-prone.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='query_route_log'"
    ).fetchone()
    if exists:
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS query_route_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash TEXT NOT NULL,
            intent TEXT NOT NULL,
            first_route TEXT,
            retrieval_path_json TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            workspace_id TEXT NOT NULL DEFAULT 'default'
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_query_route_log_created
        ON query_route_log(created_at, workspace_id)
        """
    )
    conn.commit()


def _classify_heuristic(query: str) -> IntentDecision:
    q = _norm(query)
    rules: list[tuple[Intent, float, str, tuple[str, ...]]] = [
        ("recent_activity", 0.86, "marcadores temporais/recentes", ("ultima", "ultimas", "recente", "hoje", "ontem", "atividade", "o que aconteceu", "claude")),
        ("decision", 0.84, "pergunta sobre decisao/preferencia", ("decidido", "decisao", "decisão", "preferencia", "preferência", "escolhemos")),
        ("learning", 0.82, "pergunta sobre aprendizado/padroes", ("aprendizado", "aprendemos", "licao", "lição", "padrao", "padrão", "patterns")),
        ("document", 0.82, "pergunta documental", ("documento", "pdf", "docx", "markdown", "arquivo", "citacao", "citação", "chunk")),
        ("code", 0.82, "pergunta de codigo", ("codigo", "código", "funcao", "função", "classe", "script", "arquivo .py", "implementacao")),
        ("causal", 0.82, "causalidade/validade temporal", ("causa", "causou", "porque", "por que", "quando era verdade", "valid_at", "invalid_at", "graphiti")),
        ("multi_hop", 0.78, "pergunta multi-hop/relacional", ("relacao", "relação", "multi-hop", "conecta", "grafo", "lightrag", "entre")),
        ("visual", 0.8, "memoria visual", ("visual", "screenshot", "captura", "imagem", "tela", "ocr")),
        ("self_state", 0.78, "estado/saude do proprio cerebro", ("saude", "saúde", "insula", "conflito", "estado atual", "current state")),
        ("operational", 0.78, "operacional/config/modelo", ("config", "modelo", "setup", "install", "operacional", "tronco", "env")),
        ("sector", 0.76, "cross-projeto/setor", ("setor", "diencefalo", "diencéfalo", "cross-projeto", "entre projetos")),
    ]
    for intent, confidence, reason, needles in rules:
        if any(needle in q for needle in needles):
            return IntentDecision(intent=intent, confidence=confidence, reason=reason)
    return IntentDecision(intent="hybrid", confidence=0.52, reason="fallback_hybrid")


def _norm(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii").lower()


def _metadata_context(collection: str, hit: dict[str, Any]) -> dict[str, Any] | None:
    metadata = hit.get("metadata") or {}
    if not metadata:
        return None
    return {
        "id": str(hit["id"]),
        "type": metadata.get("knowledge_type") or collection,
        "title": metadata.get("source_uri") or str(hit["id"]),
        "content": metadata.get("source_uri") or "",
        "source_uri": metadata.get("source_uri"),
        "parent_id": metadata.get("parent_id"),
        "parent_type": metadata.get("parent_type"),
        "score": hit.get("score"),
        "route": collection,
        "metadata": metadata,
    }


def _neuron_context(row: Any, *, score: float | None, route: str) -> dict[str, Any]:
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["label"],
        "content": row["content"] or "",
        "source_uri": row["source_file"] or f"hive_mind.db:neurons/{row['id']}",
        "score": score,
        "route": route,
        "metadata": _loads(row["metadata"]),
    }


def _context_from_legacy_result(result: dict[str, Any], *, top_k: int) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    for obs in result.get("observations", [])[:top_k]:
        context.append({
            "id": obs.get("id") or obs.get("source_file") or obs.get("title"),
            "type": obs.get("type") or obs.get("category") or "observation",
            "title": obs.get("title") or obs.get("source_file") or "Observation",
            "content": obs.get("content") or obs.get("text") or "",
            "source_uri": obs.get("source_file") or obs.get("source_uri"),
            "route": "hybrid",
        })
    for node in result.get("nodes", [])[:top_k]:
        context.append({
            "id": node.get("id") or node.get("label") or node.get("source"),
            "type": node.get("type") or "node",
            "title": node.get("label") or node.get("id") or "Node",
            "content": node.get("content") or node.get("source") or "",
            "source_uri": node.get("source") or node.get("source_file"),
            "route": "hybrid",
        })
    return context[:top_k]


def _legacy_projection(answer_context: list[dict[str, Any]]) -> dict[str, Any]:
    observations = []
    nodes = []
    for item in answer_context:
        if item.get("type") in {"decision", "learning", "document_chunk", "visual_memory", "summary", "observation"}:
            observations.append({
                "title": item.get("title"),
                "content": item.get("content"),
                "source_file": item.get("source_uri"),
                "type": item.get("type"),
            })
        else:
            nodes.append({
                "id": item.get("id"),
                "label": item.get("title"),
                "type": item.get("type"),
                "source": item.get("source_uri"),
            })
    return {"observations": observations, "nodes": nodes, "edges": []}


def _citation_from_context(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "source_uri": item.get("source_uri"),
        "offset_start": item.get("offset_start"),
        "offset_end": item.get("offset_end"),
        "parent_id": item.get("parent_id"),
        "parent_type": item.get("parent_type"),
        "score": item.get("score"),
        "route": item.get("route"),
    }


def _extract_observation_ids(data: dict[str, Any]) -> list[int]:
    payload = data.get("content") if isinstance(data, dict) else None
    ids: list[int] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                ids.append(item["id"])
    text = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
    for match in re.finditer(r"#(\d+)", text):
        ids.append(int(match.group(1)))
    return list(dict.fromkeys(ids))


def _temporal_context(search: dict[str, Any], hydrated: dict[str, Any] | None) -> list[dict[str, Any]]:
    records: list[Any] = []
    if isinstance(hydrated, dict):
        records = hydrated.get("results") or hydrated.get("content") or []
    if not isinstance(records, list):
        records = []
    context = []
    for row in records:
        if not isinstance(row, dict):
            continue
        context.append({
            "id": row.get("id"),
            "type": row.get("type") or "temporal_observation",
            "title": row.get("title") or row.get("subtitle") or f"Observation {row.get('id')}",
            "content": row.get("text") or row.get("narrative") or row.get("facts") or "",
            "source_uri": f"claude-mem:observations/{row.get('id')}",
            "score": 1.0,
            "route": "recent_activity",
            "metadata": row,
        })
    if context:
        return context
    text = json.dumps(search, ensure_ascii=False) if search else ""
    if text and text != "{}":
        return [{
            "id": "claude-mem:search",
            "type": "temporal_search",
            "title": "claude-mem search",
            "content": text[:2000],
            "source_uri": "claude-mem:/api/search",
            "score": 0.5,
            "route": "recent_activity",
        }]
    return []


def _dedupe_context(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for item in items:
        key = str(item.get("id") or item.get("source_uri") or item.get("title") or item.get("content", "")[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _dedupe_citations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for item in items:
        key = str(item.get("id") or item.get("source_uri") or item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _reranker_enabled() -> bool:
    value = os.environ.get("HIVE_RETRIEVAL_RERANKER", "").strip().lower()
    if not value or value in {"0", "false", "off", "none"}:
        return False
    return True


def _rerank(query: str, candidates: list[dict[str, Any]], path: list[RouteStep]) -> list[dict[str, Any]]:
    try:
        from integrations.llama_index.client import rerank

        ranked = rerank(query, candidates)
        path.append(RouteStep("reranker", "llama_index", "hit", 0.0, {"candidates": len(candidates)}))
        return ranked
    except Exception as exc:
        path.append(RouteStep("reranker", "llama_index", "error", 0.0, {"error": str(exc)[:160]}))
        return candidates
