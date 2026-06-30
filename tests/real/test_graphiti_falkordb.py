"""K9 fixtures reais para FalkorDB (via Graphiti).

Valida que o servico de grafo temporal responde ao probe TCP e que
`graphiti_available()` e `push_neuron()` operam contra o banco real
quando FalkorDB esta online. Em modo offline, pula limpo com motivo
nomeado. Este teste fecha o item 4 do Proximo Corte Recomendado
(`docs/12` §10): fixtures reais reutilizaveis para FalkorDB.
"""
from __future__ import annotations

import uuid

import pytest

from tests.real.service_registry import check_service


@pytest.mark.real
@pytest.mark.requires_service("falkordb")
def test_falkordb_or_skip_resolves_to_online_service():
    """A fixture `falkordb_or_skip` so cede quando o servico esta online."""
    # Se chegamos aqui, o skip ja nao pulou. O service_registry confirma.
    status = check_service("falkordb")
    assert status.ok, status.reason


@pytest.mark.real
@pytest.mark.requires_service("falkordb")
def test_graphiti_available_against_real_falkordb(falkordb_or_skip):
    """`graphiti_available()` reflete o estado real do FalkorDB."""
    from integrations.graphiti import graphiti_available

    host, port = falkordb_or_skip
    # graphiti_available() consulta o servico via TCP (nao usa o fixture
    # diretamente). Se o fixture passou, a checagem tem que bater.
    assert graphiti_available(), f"FalkorDB offline em {host}:{port}"


@pytest.mark.real
@pytest.mark.requires_service("falkordb")
def test_graphiti_push_neuron_writes_to_real_backend(falkordb_or_skip):
    """`push_neuron()` grava no FalkorDB real e devolve `True`."""
    from integrations.graphiti import push_neuron, search_graph

    neuron_id = f"test-neuron-{uuid.uuid4().hex[:12]}"
    content = "FalkorDB fixture real grava neuronio via push_neuron."
    try:
        ok = push_neuron(neuron_id, content, source="tests/real")
        assert ok, f"push_neuron falhou em {falkordb_or_skip}"
    finally:
        # Limpa o neuronio criado para nao poluir o grafo entre runs.
        try:
            from integrations.graphiti import _graphiti

            if _graphiti() is not None:
                _graphiti().driver.execute_query(
                    "MATCH (n {id: $id}) DETACH DELETE n", id=neuron_id
                )
        except Exception:
            pass
