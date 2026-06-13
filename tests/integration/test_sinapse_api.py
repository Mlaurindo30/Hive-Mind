"""Integração: REST API (scripts/sinapse-api.py) — contrato ATUAL.

Valida os endpoints reais da API de nuvem com FastAPI TestClient:
  - GET  /api/v1/health           (público)
  - POST /api/v1/query            (autenticado, leitura)
  - POST /api/v1/neurons/export   (autenticado, leitura)
  - POST /api/v1/observations     (autenticado — só checa enforcement de auth)

Foco em auth e endpoints de leitura para não poluir o banco real.
Gated por HIVE_RUN_INTEGRATION=1 (ver tests/integration/__init__.py / conftest).
"""

import os

import pytest

# Chave de API definida ANTES de carregar o módulo (a API lê HIVE_MIND_API_KEY).
API_KEY = "integration_test_secret_key_123"
os.environ["HIVE_MIND_API_KEY"] = API_KEY

if os.environ.get("HIVE_RUN_INTEGRATION") != "1":
    pytest.skip(
        "Integração real desabilitada. Defina HIVE_RUN_INTEGRATION=1 para rodar.",
        allow_module_level=True,
    )

from pathlib import Path
import importlib.util

# Dependências opcionais da API — pula o módulo inteiro se ausentes.
pytest.importorskip("fastapi")
pytest.importorskip("slowapi")
pytest.importorskip("cryptography")

from fastapi.testclient import TestClient

# Carrega scripts/sinapse-api.py dinamicamente para obter a instância da app.
_api_script = Path(__file__).resolve().parents[2] / "scripts" / "sinapse-api.py"
spec = importlib.util.spec_from_file_location("sinapse_api", _api_script)
api_mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(api_mod)
except ImportError as exc:  # dependência transitiva ausente
    pytest.skip(f"Dependência da API ausente: {exc}", allow_module_level=True)

app = api_mod.app
client = TestClient(app)

_AUTH = {"Authorization": f"Bearer {API_KEY}"}


def test_health_is_public():
    """GET /api/v1/health é público e responde online."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "online"


def test_query_requires_auth():
    """POST /api/v1/query sem token → 401/403."""
    r = client.post("/api/v1/query", json={"query": "x"})
    assert r.status_code in (401, 403)

    r = client.post(
        "/api/v1/query",
        json={"query": "x"},
        headers={"Authorization": "Bearer wrong_token"},
    )
    assert r.status_code == 401


def test_observations_requires_auth():
    """POST /api/v1/observations sem token → 401/403 (não grava nada)."""
    r = client.post("/api/v1/observations", json={"title": "t", "content": "c"})
    assert r.status_code in (401, 403)


def test_export_requires_auth():
    """POST /api/v1/neurons/export sem token → 401/403."""
    r = client.post("/api/v1/neurons/export", json={})
    assert r.status_code in (401, 403)


def test_metrics_requires_auth():
    r = client.get("/api/v1/metrics")
    assert r.status_code in (401, 403)


def test_query_endpoint_authenticated():
    """POST /api/v1/query autenticado retorna a lista de resultados."""
    r = client.post("/api/v1/query", json={"query": "memory", "limit": 3}, headers=_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert isinstance(data["results"], list)


def test_export_endpoint_authenticated():
    """POST /api/v1/neurons/export autenticado retorna o envelope de export."""
    r = client.post("/api/v1/neurons/export", json={"redact": True}, headers=_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "neurons" in data
    assert "count" in data
    assert isinstance(data["neurons"], list)


def test_metrics_endpoint_authenticated():
    r = client.get("/api/v1/metrics", headers=_AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in {"online", "degraded"}
    assert data["uptime_seconds"] >= 0
    assert data["database"]["quick_check"] == "ok"
    assert data["database"]["foreign_key_violations"] == 0
    assert data["indexes"]["hnsw"] is True
