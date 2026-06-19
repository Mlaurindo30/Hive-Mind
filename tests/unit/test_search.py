"""F5.2 core/search — testes unitários (doc 08 §11/F5.2).

Cobre: project_topic_from_path, busca full-text, fallback semântico,
filtro por projeto, limite top_k. Não requer fastembed/hnswlib.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.search import project_topic_from_path, search_neurons

_DDL = """
CREATE TABLE neurons (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'fact',
    source_file TEXT,
    content TEXT,
    metadata JSON,
    indexed_at TIMESTAMP
);
"""


def _conn(rows: list[dict] | None = None):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(_DDL)
    if rows:
        for r in rows:
            c.execute(
                "INSERT INTO neurons (id, label, type, source_file, content, metadata) "
                "VALUES (:id, :label, :type, :source_file, :content, :metadata)",
                r,
            )
        c.commit()
    return c


# --------------------------------------------------------------------------- #
# project_topic_from_path                                                      #
# --------------------------------------------------------------------------- #

def test_extrai_projeto_e_topico_path_completo():
    sf = "cerebro/cortex/temporal/Hive-Mind/atlas/neuronio-abc.md"
    assert project_topic_from_path(sf) == ("Hive-Mind", "atlas")


def test_extrai_apenas_projeto_sem_topico():
    sf = "cerebro/cortex/temporal/Hive-Mind"
    assert project_topic_from_path(sf) == ("Hive-Mind", "")


def test_sem_temporal_retorna_vazios():
    assert project_topic_from_path("cerebro/atoms/fact-abc.md") == ("", "")


def test_path_vazio_retorna_vazios():
    assert project_topic_from_path("") == ("", "")


def test_backslash_normalizado():
    sf = "cerebro\\cortex\\temporal\\Proj\\topic\\n.md"
    assert project_topic_from_path(sf) == ("Proj", "topic")


# --------------------------------------------------------------------------- #
# search_neurons — modo text (sem hnswlib/fastembed)                          #
# --------------------------------------------------------------------------- #

def _rows():
    return [
        {
            "id": "n1", "label": "Python asyncio overview", "type": "fact",
            "source_file": "cerebro/cortex/temporal/Hive-Mind/python/neuronio-n1.md",
            "content": "asyncio event loop explained", "metadata": None,
        },
        {
            "id": "n2", "label": "Docker compose networks", "type": "fact",
            "source_file": "cerebro/cortex/temporal/Hive-Mind/infra/neuronio-n2.md",
            "content": "container networking basics", "metadata": '{"aliases": ["docker-net"]}',
        },
        {
            "id": "n3", "label": "ComfyUI workflow", "type": "fact",
            "source_file": "cerebro/cortex/temporal/ComfyUI/workflows/neuronio-n3.md",
            "content": "stable diffusion node graph", "metadata": None,
        },
    ]


def test_text_mode_retorna_resultados():
    c = _conn(_rows())
    results = search_neurons(c, "asyncio", mode="text")
    assert any(r["label"] == "Python asyncio overview" for r in results)
    c.close()


def test_text_mode_extrai_projeto_topico():
    c = _conn(_rows())
    results = search_neurons(c, "asyncio", mode="text")
    r = next(r for r in results if r["label"] == "Python asyncio overview")
    assert r["project"] == "Hive-Mind"
    assert r["topic"] == "python"
    c.close()


def test_text_mode_aliases_do_metadata():
    c = _conn(_rows())
    results = search_neurons(c, "Docker", mode="text")
    r = next(r for r in results if r["label"] == "Docker compose networks")
    assert r["aliases"] == ["docker-net"]
    c.close()


def test_text_mode_score_none():
    c = _conn(_rows())
    results = search_neurons(c, "asyncio", mode="text")
    assert all(r["score"] is None for r in results)
    c.close()


def test_text_mode_filtra_por_projeto():
    c = _conn(_rows())
    # "stable diffusion" aparece só no n3 (ComfyUI)
    results = search_neurons(c, "stable diffusion", mode="text", project="ComfyUI")
    assert len(results) == 1
    assert results[0]["project"] == "ComfyUI"
    c.close()


def test_text_mode_top_k():
    c = _conn(_rows())
    results = search_neurons(c, "neuronio", mode="text", top_k=2)
    assert len(results) <= 2
    c.close()


def test_text_mode_sem_resultados():
    c = _conn(_rows())
    results = search_neurons(c, "xyzzy_inexistente_42", mode="text")
    assert results == []
    c.close()


# --------------------------------------------------------------------------- #
# search_neurons — modo semantic com HNSW indisponível → fallback             #
# --------------------------------------------------------------------------- #

def test_semantic_fallback_quando_hnsw_ausente(monkeypatch):
    """Sem índice HNSW fresh, deve cair em full-text."""
    monkeypatch.setattr("core.search._hnsw_is_fresh", lambda: False)
    c = _conn(_rows())
    results = search_neurons(c, "asyncio", mode="semantic")
    # Deve retornar resultado via full-text
    assert any(r["label"] == "Python asyncio overview" for r in results)
    c.close()


def test_semantic_campo_score_none_no_fallback(monkeypatch):
    monkeypatch.setattr("core.search._hnsw_is_fresh", lambda: False)
    c = _conn(_rows())
    results = search_neurons(c, "asyncio", mode="semantic")
    assert all(r["score"] is None for r in results)
    c.close()
