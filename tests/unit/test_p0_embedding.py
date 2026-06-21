"""P0 — testes do sistema de embedding configurável (fastembed / ollama).

Verifica que:
  1. embed_text() retorna lista de floats com dimensão correta (backend atual)
  2. Mesmo texto → mesmo vetor (determinismo)
  3. Textos diferentes → vetores diferentes
  4. OllamaEmbedder pode ser instanciado e tem interface correta
  5. EMBED_BACKEND=ollama seleciona OllamaEmbedder em get_embedder()
  6. Se Ollama estiver rodando, testa embedding real (skip caso contrário)
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.database import (
    OllamaEmbedder,
    embed_text,
    get_embedder,
    EMBED_BACKEND,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ollama_running() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Testes do backend ativo (fastembed ou ollama)
# ---------------------------------------------------------------------------

def test_embed_text_retorna_lista_de_floats():
    vec = embed_text("teste de embedding")
    assert isinstance(vec, list), "embed_text deve retornar list"
    assert all(isinstance(x, float) for x in vec), "todos os elementos devem ser float"
    assert len(vec) > 0


def test_embed_text_dimensao_coerente():
    """Dimensão deve ser consistente entre chamadas (mesmo backend)."""
    v1 = embed_text("primeiro texto")
    v2 = embed_text("segundo texto completamente diferente")
    assert len(v1) == len(v2), f"dimensões inconsistentes: {len(v1)} vs {len(v2)}"


def test_embed_text_determinismo():
    """Mesmo texto → mesmo vetor."""
    text = "memória semântica determinística"
    v1 = embed_text(text)
    v2 = embed_text(text)
    assert v1 == v2, "embed_text deve ser determinístico"


def test_embed_text_textos_distintos_diferem():
    """Textos diferentes devem gerar vetores distintos."""
    v1 = embed_text("python asyncio event loop")
    v2 = embed_text("receita de bolo de chocolate")
    assert v1 != v2, "textos semanticamente diferentes não podem ter vetores idênticos"


def test_embed_text_texto_longo_truncado():
    """Texto maior que 5000 chars não deve falhar."""
    long_text = "a" * 10_000
    vec = embed_text(long_text)
    assert isinstance(vec, list)
    assert len(vec) > 0


# ---------------------------------------------------------------------------
# Testes da classe OllamaEmbedder (interface, sem rede)
# ---------------------------------------------------------------------------

def test_ollama_embedder_interface():
    """OllamaEmbedder expõe embed() que retorna um iterador."""
    embedder = OllamaEmbedder("http://localhost:11434", "nomic-embed-text:latest")
    assert hasattr(embedder, "embed"), "OllamaEmbedder deve ter método embed()"


def test_embed_backend_env_var(monkeypatch):
    """EMBED_BACKEND=ollama faz get_embedder() retornar OllamaEmbedder."""
    import core.database as db

    original = db._embedder
    try:
        db._embedder = None
        monkeypatch.setenv("EMBED_BACKEND", "ollama")
        monkeypatch.setattr(db, "EMBED_BACKEND", "ollama")

        embedder = db.get_embedder()
        assert isinstance(embedder, OllamaEmbedder), (
            f"esperado OllamaEmbedder, got {type(embedder)}"
        )
    finally:
        db._embedder = original


def test_embed_backend_fastembed(monkeypatch):
    """EMBED_BACKEND=fastembed faz get_embedder() retornar instância de fastembed."""
    import core.database as db

    original = db._embedder
    try:
        db._embedder = None
        monkeypatch.setenv("EMBED_BACKEND", "fastembed")
        monkeypatch.setattr(db, "EMBED_BACKEND", "fastembed")

        embedder = db.get_embedder()
        if embedder is not None:
            assert not isinstance(embedder, OllamaEmbedder), (
                "fastembed backend não deve retornar OllamaEmbedder"
            )
    finally:
        db._embedder = original


# ---------------------------------------------------------------------------
# Teste live do Ollama (skip se não estiver rodando)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _ollama_running(), reason="Ollama não está rodando em localhost:11434")
def test_ollama_embedder_live_nomic():
    """Testa embedding real via Ollama nomic-embed-text (requer Ollama rodando)."""
    embedder = OllamaEmbedder("http://localhost:11434", "nomic-embed-text:latest")
    vecs = list(embedder.embed(["teste de embedding semântico"]))
    assert len(vecs) == 1
    vec = vecs[0]
    assert isinstance(vec, list)
    assert len(vec) == 768, f"nomic-embed-text deve gerar 768d, got {len(vec)}"
    assert all(isinstance(x, (int, float)) for x in vec)


@pytest.mark.skipif(not _ollama_running(), reason="Ollama não está rodando em localhost:11434")
def test_ollama_embedder_live_batch():
    """OllamaEmbedder processa múltiplos textos sequencialmente."""
    embedder = OllamaEmbedder("http://localhost:11434", "nomic-embed-text:latest")
    texts = ["primeiro texto", "segundo texto", "terceiro texto"]
    vecs = list(embedder.embed(texts))
    assert len(vecs) == 3
    assert all(len(v) == 768 for v in vecs)
    assert vecs[0] != vecs[1], "textos distintos devem gerar vetores distintos"
