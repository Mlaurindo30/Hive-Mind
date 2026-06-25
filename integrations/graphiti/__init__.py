"""Graphiti — órgão do lóbulo temporal do cérebro do Hive-Mind.

Fornece grafo de causalidade temporal (com janelas de validade) sobre
FalkorDB, complementando o tracking de eventos do `claude-mem` (tálamo
sensorial do mesmo lobo). Juntos, dão ao cérebro a capacidade de responder
"o que era verdade sobre X em tal data".

API pública (re-exportada de `client.py`):

- `push_neuron(neuron_id, content, source="dream")` — indexa um neurônio.
- `search_graph(query, num_results=10)` — busca edges com janelas de validade.
- `graphiti_available()` — checa FalkorDB + circuit breaker.
- `assert_health()` — smoke test (FalkorDB + modelos Ollama + write/read).
- `circuit_state()` — estado do circuit breaker.

Robustez: smoke test, circuit breaker, retry com backoff, persistência
via JSON-lines no lóbulo temporal quando FalkorDB offline.

Clientes deste módulo NÃO devem importar `client` diretamente — use
este `__init__.py` para que re-organizações internas não quebrem callers.
Para testes whitebox, os internos também são re-exportados (ver `__all__`).
"""
from integrations.graphiti import client as _client
from integrations.graphiti.client import (
    _build_client,
    _circuit_record_failure,
    _circuit_record_success,
    _fallback_append,
    _fallback_dir,
    _fallback_path,
    _fallback_search,
    _graphiti,
    _retry_with_backoff,
    assert_health,
    circuit_state,
    graphiti_available,
    ollama_model_exists,
    push_neuron,
    reset_circuit,
    search_graph,
)

__all__ = [
    # Public API
    "push_neuron",
    "search_graph",
    "graphiti_available",
    "ollama_model_exists",
    "assert_health",
    "circuit_state",
    "reset_circuit",
    # Whitebox internals (testes)
    "_build_client",
    "_circuit_record_failure",
    "_circuit_record_success",
    "_fallback_append",
    "_fallback_dir",
    "_fallback_path",
    "_fallback_search",
    "_graphiti",
    "_retry_with_backoff",
    "_client",
]
