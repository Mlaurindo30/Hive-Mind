"""Integration gate for REST /api/v1/query hybrid Context Fusion.

This exercises the FastAPI entrypoint with the real sinapse-memory fusion
bridge. It catches the regression where the API called RetrievalRouter without
`sinapse_query_fn`, making hybrid REST queries return empty results while MCP
queries still worked.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


API_KEY = "integration_test_secret_key_123"
os.environ["HIVE_MIND_API_KEY"] = API_KEY

if os.environ.get("HIVE_RUN_INTEGRATION") != "1":
    pytest.skip(
        "Integração real desabilitada. Defina HIVE_RUN_INTEGRATION=1 para rodar.",
        allow_module_level=True,
    )

pytest.importorskip("fastapi")
pytest.importorskip("slowapi")
pytest.importorskip("cryptography")

from fastapi.testclient import TestClient


_api_script = Path(__file__).resolve().parents[2] / "scripts" / "services" / "sinapse-api.py"
spec = importlib.util.spec_from_file_location("sinapse_api_hybrid_tests", _api_script)
api_mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(api_mod)
except ImportError as exc:
    pytest.skip(f"Dependência da API ausente: {exc}", allow_module_level=True)

client = TestClient(api_mod.app)
_AUTH = {"Authorization": f"Bearer {API_KEY}"}


@pytest.fixture(autouse=True)
def _ensure_api_key(monkeypatch):
    monkeypatch.setenv("HIVE_MIND_API_KEY", API_KEY)


def test_api_query_hybrid_uses_real_context_fusion(ensure_backends):
    response = client.post(
        "/api/v1/query",
        json={
            "query": "Hive-Mind knowledge promotion architecture",
            "intent": "hybrid",
            "limit": 3,
        },
        headers=_AUTH,
    )

    assert response.status_code == 200
    data = response.json()
    assert "hybrid:context_fusion_indisponivel" not in data.get("missing_context", [])
    assert data["results"], data
    assert data["confidence"] > 0
    assert any(
        step.get("route") == "hybrid"
        and step.get("backend") == "sinapse_query/context_fusion"
        and step.get("status") == "hit"
        for step in data.get("retrieval_path", [])
    ), data.get("retrieval_path")
