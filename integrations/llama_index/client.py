"""Thin LlamaIndex adapter used by RetrievalRouter.

The project keeps its own routing contract. LlamaIndex is an optional utility
layer for health checks and lightweight candidate reranking, never the hidden
source of routing truth.
"""
from __future__ import annotations

import re
from typing import Any


def assert_health(strict: bool = False) -> dict[str, Any]:
    try:
        import llama_index.core  # noqa: F401

        return {"ok": True, "service": "llama_index"}
    except Exception as exc:
        if strict:
            raise
        return {"ok": False, "service": "llama_index", "reason": str(exc)}


def rerank(query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Local lexical rerank with LlamaIndex availability gate.

    This is intentionally deterministic and fail-open. It avoids introducing a
    hidden remote cross-encoder while still giving K7 a stable reranker hook.
    """
    health = assert_health(strict=False)
    if not health.get("ok"):
        return candidates

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


def _terms(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÿ0-9_]{3,}", text.lower())
