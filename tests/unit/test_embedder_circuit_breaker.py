"""Circuit breaker do OllamaEmbedder (core/database.py).

Regressão do teste de instalação limpa (2026-07-02): numa máquina sem Ollama,
`graphify update` pagava retry+backoff por nó (~2.5s x ~800 nós ≈ 40 min de
sleep) e o install parecia travado. Conexão recusada deve abrir o breaker:
falha imediata com EmbedderOffline, sem retry.
"""
import time

import pytest

from core.database import EmbedderOffline, OllamaEmbedder

# Porta 1 em loopback: conexão recusada instantânea, sem depender de rede.
DEAD_ENDPOINT = "http://127.0.0.1:1"


def test_connection_refused_opens_breaker_fast():
    emb = OllamaEmbedder(DEAD_ENDPOINT, "any-model")
    start = time.monotonic()
    with pytest.raises(EmbedderOffline):
        list(emb.embed("hello"))
    elapsed = time.monotonic() - start
    assert emb.offline is True
    # Sem breaker seriam >=2.4s só de backoff; com ele, sub-segundo.
    assert elapsed < 2.0, f"breaker não abriu rápido: {elapsed:.2f}s"


def test_breaker_stays_open_and_skips_retries():
    emb = OllamaEmbedder(DEAD_ENDPOINT, "any-model")
    with pytest.raises(EmbedderOffline):
        list(emb.embed("first"))
    start = time.monotonic()
    for _ in range(50):
        assert emb._post(["x"]) is None
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"chamadas com breaker aberto não são imediatas: {elapsed:.2f}s"


def test_timeout_is_not_treated_as_unreachable():
    assert OllamaEmbedder._is_unreachable(TimeoutError()) is False
    assert OllamaEmbedder._is_unreachable(ConnectionRefusedError()) is True
