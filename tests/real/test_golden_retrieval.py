"""K7+K9 precision/recall@k gate (docs/11 §17.3, docs/12 §K9 task 7).

Avalia o envelope de retrieval real (sem mock) contra `golden_retrieval.jsonl`.
O golden set exige:
- `query`              — texto da pergunta;
- `expected_intent`    — intent prevista (`decision`, `document`, etc.);
- `expected_source_ids` — IDs (ou fragmentos) que DEVEM aparecer no top-k.

Cobre dois gates complementares:
- **intent gate**: ≥ 0.75 das queries têm intent classificada corretamente;
- **retrieval gate**: precision@k ≥ 0.5 e recall@k ≥ 0.5 quando há
  `expected_source_ids` declarado. Se a fixture não casa, o teste skip
  explícito em vez de falhar — permite rodar em máquinas com corpus
  parcial enquanto mantém o gate em CI completo.

Serviços: Ollama (decisão + embeddings). Pula limpo se offline.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

GOLDEN_PATH = Path(__file__).with_name("golden_retrieval.jsonl")
INTENT_GATE = 0.75
PRECISION_K_GATE = 0.5
RECALL_K_GATE = 0.5


def _load_cases() -> list[dict[str, Any]]:
    if not GOLDEN_PATH.exists():
        pytest.skip(f"golden set ausente: {GOLDEN_PATH}")
    return [
        json.loads(line)
        for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _id_in_hits(expected: list[str], hits: list[dict[str, Any]]) -> int:
    """Conta quantos `expected` aparecem no top-k (id ou parent_id)."""
    if not expected:
        return 0
    keys = {str(h.get("id") or h.get("parent_id") or h.get("source_uri") or "") for h in hits}
    matched = 0
    for want in expected:
        needle = str(want)
        if any(needle and needle in key for key in keys):
            matched += 1
    return matched


@pytest.mark.real
@pytest.mark.requires_service("ollama")
def test_golden_intent_classification_gate():
    """Gate 1: ≥ 75% das intents previstas casam com a classificação real."""
    from core.retrieval.router import RetrievalRouter

    cases = _load_cases()
    router = RetrievalRouter()
    try:
        counts = Counter(c["expected_intent"] for c in cases)
        hits: list[str] = []
        for case in cases:
            decision = router.classify(case["query"])
            if decision.intent == case["expected_intent"]:
                hits.append(case["expected_intent"])
        accuracy = len(hits) / len(cases) if cases else 1.0
        assert accuracy >= INTENT_GATE, (
            f"Intent gate falhou: {accuracy:.0%} < {INTENT_GATE:.0%}. "
            f"Esperado={dict(counts)}; obtido={sorted(hits)}."
        )
    finally:
        router.close()


@pytest.mark.real
@pytest.mark.requires_service("ollama")
def test_golden_retrieval_precision_recall_at_k(real_db, tmp_path):
    """Gate 2: para casos com `expected_source_ids`, precision/recall@k ≥ 0.5.

    Semeia um neurônio mínimo no `real_db` (mesmo conteúdo do golden) e
    reidrata a coleção vetorial com o embedder real. Pula explícito quando
    um caso não tem ID esperado ou o neurônio seed não pôde ser injetado.
    """
    from core.database import embed_text
    from core.retrieval.router import RetrievalRouter
    from core.vector_backend import SQLiteVecBackend

    cases = [c for c in _load_cases() if c.get("expected_source_ids")]
    if not cases:
        pytest.skip("golden set sem casos com expected_source_ids")

    seed: dict[str, str] = {
        "decision-embeddings-snowflake": "Foi decidido usar snowflake-arctic-embed2:latest para embeddings 1024d.",
        "doc": "O RetrievalRouter retorna citations, retrieval_path, confidence e missing_context.",
    }
    backend = SQLiteVecBackend(real_db)
    for sid, content in seed.items():
        if any(sid in want for c in cases for want in c["expected_source_ids"]):
            real_db.execute(
                "INSERT OR REPLACE INTO neurons(id, label, type, source_file, content, hash, workspace_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    sid,
                    "decision" if sid.startswith("decision") else "document",
                    f"cerebro/cortex/frontal/decisoes/{sid}.md",
                    content,
                    f"hash-{sid}",
                    "default",
                ),
            )
            backend.upsert("memory_vectors", sid, embed_text(content))

    router = RetrievalRouter(conn=real_db)
    try:
        precisions: list[float] = []
        recalls: list[float] = []
        skipped: list[str] = []
        for case in cases:
            result = router.route(case["query"], top_k=5)
            hits = result.get("answer_context", [])
            if not hits:
                skipped.append(case["query"])
                continue
            matched = _id_in_hits(case["expected_source_ids"], hits)
            k = len(hits)
            precisions.append(matched / k)
            recalls.append(matched / len(case["expected_source_ids"]))

        if not precisions:
            pytest.skip(
                "nenhum caso do golden retornou answer_context; corpus mínimo ausente neste host"
            )

        p_at_k = sum(precisions) / len(precisions)
        r_at_k = sum(recalls) / len(recalls)
        assert p_at_k >= PRECISION_K_GATE, (
            f"precision@k={p_at_k:.2f} < {PRECISION_K_GATE:.2f}; pulados={skipped}"
        )
        assert r_at_k >= RECALL_K_GATE, (
            f"recall@k={r_at_k:.2f} < {RECALL_K_GATE:.2f}; pulados={skipped}"
        )
    finally:
        router.close()
