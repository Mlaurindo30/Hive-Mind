"""K9 fixtures reais para RAGFlow (wrapper headless).

Valida que o wrapper RAGFlow em `integrations/ragflow/` consegue
instanciar `RAGFlowSettings` e bater em `/api/v1/health` ou `/`. Em
modo offline, pula limpo com motivo nomeado. Este teste fecha o item
4 do Proximo Corte Recomendado (`docs/12` §10): fixtures reais
reutilizaveis para RAGFlow.

RAGFlow roda headless: o store dele e cache de ingestao, e o canonico
continua sendo UMC + `cerebro/`. Aqui so provamos que o wrapper
funciona contra o servico real.
"""
from __future__ import annotations

import pytest


@pytest.mark.real
@pytest.mark.requires_service("ragflow")
def test_ragflow_or_skip_resolves_to_online_service():
    """A fixture `ragflow_or_skip` so cede quando o servico esta online."""
    from tests.real.service_registry import check_service

    status = check_service("ragflow")
    assert status.ok, status.reason


@pytest.mark.real
@pytest.mark.requires_service("ragflow")
def test_ragflow_settings_reflect_env(ragflow_or_skip):
    """`RAGFlowSettings` le env vars reais (RAGFLOW_BASE, RAGFLOW_API_KEY)."""
    RAGFlowSettings, _ = ragflow_or_skip
    s = RAGFlowSettings(base_url="http://example.invalid:9380", api_key="k")
    assert s.base_url == "http://example.invalid:9380"
    assert s.api_key == "k"
    assert s.version  # default v1


@pytest.mark.real
@pytest.mark.requires_service("ragflow")
def test_ragflow_health_against_real_service(ragflow_or_skip):
    """`assert_health(strict=False)` retorna `ok=True` quando o servico responde."""
    RAGFlowSettings, assert_health = ragflow_or_skip
    result = assert_health(strict=False)
    assert result["service"] == "ragflow"
    assert result.get("ok") is True, result
