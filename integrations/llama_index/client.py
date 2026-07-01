"""Thin LlamaIndex adapter used by RetrievalRouter.

The project keeps its own routing contract. LlamaIndex is an optional utility
layer for health checks and lightweight candidate reranking, never the hidden
source of routing truth.
"""
from __future__ import annotations

from functools import lru_cache
import os
import re
from typing import Any


def assert_health(strict: bool = False) -> dict[str, Any]:
    try:
        import llama_index.core  # noqa: F401

        health: dict[str, Any] = {"ok": True, "service": "llama_index"}
        config = _cross_encoder_config()
        if config:
            health["reranker_provider"] = config["provider"]
            health["reranker_model"] = config["model"]
            try:
                import sentence_transformers  # noqa: F401

                health["reranker_available"] = True
            except Exception as exc:
                health["reranker_available"] = False
                health["reranker_reason"] = str(exc)
        return health
    except Exception as exc:
        if strict:
            raise
        return {"ok": False, "service": "llama_index", "reason": str(exc)}


def rerank(query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Local rerank with LlamaIndex availability gate.

    Default mode is deterministic lexical rerank. If HIVE_RERANKER_PROVIDER and
    HIVE_RERANKER_MODEL are set, a local sentence-transformers CrossEncoder is
    used first. Every path is fail-open back to lexical/original order.
    """
    health = assert_health(strict=False)
    if not health.get("ok"):
        return candidates

    config = _cross_encoder_config()
    if config:
        ranked = _cross_encoder_rerank(query, candidates, config["model"])
        if ranked is not None:
            return ranked

    return _lexical_rerank(query, candidates)


def _lexical_rerank(query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_terms = set(_terms(query))
    if not query_terms:
        return candidates

    def score(item: dict[str, Any]) -> float:
        text = " ".join(str(item.get(k) or "") for k in ("title", "content", "source_uri"))
        terms = set(_terms(text))
        overlap = len(query_terms & terms)
        base = float(item.get("score") or 0.0)
        return overlap + base

    return sorted(candidates, key=score, reverse=True)


def _cross_encoder_config() -> dict[str, str] | None:
    provider = os.environ.get("HIVE_RERANKER_PROVIDER", "").strip().lower()
    model = os.environ.get("HIVE_RERANKER_MODEL", "").strip()
    if not provider or not model:
        return None
    if provider not in {
        "sentence-transformers",
        "sentence_transformers",
        "cross-encoder",
        "cross_encoder",
        "local",
    }:
        return None
    return {"provider": provider, "model": model}


def _cross_encoder_rerank(
    query: str,
    candidates: list[dict[str, Any]],
    model_name: str,
) -> list[dict[str, Any]] | None:
    try:
        model = _load_cross_encoder(model_name)
        pairs = [(query, _candidate_text(item)) for item in candidates]
        if not pairs:
            return candidates
        raw_scores = model.predict(pairs)
        scored: list[tuple[float, int, dict[str, Any]]] = []
        for index, (item, raw_score) in enumerate(zip(candidates, raw_scores, strict=False)):
            copied = dict(item)
            copied["rerank_score"] = float(raw_score)
            copied["rerank_provider"] = "sentence-transformers"
            copied["rerank_model"] = model_name
            scored.append((float(raw_score), index, copied))
        return [item for _, _, item in sorted(scored, key=lambda row: (row[0], -row[1]), reverse=True)]
    except Exception:
        return None


@lru_cache(maxsize=2)
def _load_cross_encoder(model_name: str) -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name, max_length=512)


def _candidate_text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(k) or "") for k in ("title", "content", "source_uri"))


def _terms(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÿ0-9_]{3,}", text.lower())
