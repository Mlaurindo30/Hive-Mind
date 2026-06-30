"""K7 RetrievalRouter real tests.

Uses the real SQLite schema, sqlite-vec and Ollama embeddings. No mocked
retrievers are used for the acceptance paths.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.real
@pytest.mark.requires_service("ollama")
def test_retrieval_router_routes_decision_to_memory_vectors(real_db):
    from core.database import embed_text
    from core.retrieval.router import RetrievalRouter
    from core.vector_backend import SQLiteVecBackend

    real_db.execute(
        """
        INSERT INTO neurons(id, label, type, source_file, content, hash, workspace_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "decision-embeddings-snowflake",
            "Decisao embeddings snowflake",
            "decision",
            "cerebro/cortex/frontal/decisoes/embeddings.md",
            "Foi decidido usar snowflake-arctic-embed2:latest para embeddings 1024d.",
            "hash-decision-snowflake",
            "default",
        ),
    )
    SQLiteVecBackend(real_db).upsert(
        "memory_vectors",
        "decision-embeddings-snowflake",
        embed_text("decisao embeddings snowflake arctic embed2 1024"),
    )

    router = RetrievalRouter(conn=real_db)
    result = router.route("o que foi decidido sobre embeddings snowflake?", top_k=3)

    assert result["intent"] == "decision"
    assert result["answer_context"], result
    assert result["answer_context"][0]["id"] == "decision-embeddings-snowflake"
    assert result["citations"][0]["source_uri"].endswith("embeddings.md")
    assert result["retrieval_path"][0]["backend"] == "memory_vectors"
    assert result["confidence"] > 0
    assert isinstance(result["missing_context"], list)

    from core.search import route_retrieval

    via_search = route_retrieval(
        real_db,
        "o que foi decidido sobre embeddings snowflake?",
        intent="decision",
        top_k=3,
    )
    assert via_search["retrieval_path"][0]["backend"] == "memory_vectors"


@pytest.mark.real
@pytest.mark.requires_service("ollama")
def test_retrieval_router_routes_document_to_document_pipeline(real_db, tmp_path):
    from core.document_pipeline import DocumentPipeline
    from core.retrieval.router import RetrievalRouter

    doc = tmp_path / "retrieval-architecture.md"
    doc.write_text(
        "# Arquitetura de recuperacao\n\n"
        "O RetrievalRouter retorna citations, retrieval_path, confidence e missing_context.\n",
        encoding="utf-8",
    )
    pipeline = DocumentPipeline(real_db)
    ingested = pipeline.ingest(doc, project="Hive-Mind")

    result = RetrievalRouter(conn=real_db, project="Hive-Mind").route(
        "cite o documento sobre arquitetura de recuperacao", top_k=3
    )

    assert result["intent"] == "document"
    assert result["answer_context"], result
    assert result["answer_context"][0]["type"] == "document_chunk"
    assert result["answer_context"][0]["parent_id"] == ingested.document_id
    assert result["citations"][0]["offset_start"] is not None
    assert "document_vectors" in {step["backend"] for step in result["retrieval_path"]}


@pytest.mark.real
def test_retrieval_router_golden_intents():
    from core.retrieval.router import RetrievalRouter

    cases = [
        json.loads(line)
        for line in (Path(__file__).with_name("golden_retrieval.jsonl")).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    router = RetrievalRouter()
    try:
        correct = 0
        for case in cases:
            decision = router.classify(case["query"])
            if decision.intent == case["expected_intent"]:
                correct += 1
        assert correct / len(cases) >= 0.75
    finally:
        router.close()
