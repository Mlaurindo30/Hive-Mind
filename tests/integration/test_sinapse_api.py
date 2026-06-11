import os
import sys
import time
import threading

API_KEY = "integration_test_secret_key_123"

# Configura as variáveis de ambiente ANTES de carregar o módulo
os.environ["SINAPSE_API_KEY"] = API_KEY
os.environ["SINAPSE_DRY_RUN"] = "true"

import pytest
from pathlib import Path
import importlib.util

# Dependências opcionais da API — pula o módulo inteiro se ausentes,
# em vez de quebrar a coleta do pytest.
pytest.importorskip("fastapi")
pytest.importorskip("slowapi")
pytest.importorskip("cryptography")
uvicorn = pytest.importorskip("uvicorn")

from fastapi.testclient import TestClient

# Carrega scripts/sinapse-api.py dinamicamente para obter a instância da app
_api_script = Path(__file__).resolve().parents[2] / "scripts" / "sinapse-api.py"
spec = importlib.util.spec_from_file_location("sinapse_api", _api_script)
api_mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(api_mod)
except ImportError as exc:  # dependência transitiva ausente
    pytest.skip(f"Dependência da API ausente: {exc}", allow_module_level=True)
app = api_mod.app

client = TestClient(app)


class BackgroundServer(threading.Thread):
    def __init__(self, app, host="127.0.0.1", port=8001):
        super().__init__()
        config = uvicorn.Config(app, host=host, port=port, log_level="error")
        self.server = uvicorn.Server(config)
        self.daemon = True

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


@pytest.fixture(autouse=True)
def force_dry_run_for_api_tests():
    orig_dry_run = api_mod.sm.DRY_RUN
    api_mod.sm.DRY_RUN = True
    yield
    api_mod.sm.DRY_RUN = orig_dry_run


def test_unauthorized_access():

    """Garante que chamadas sem token ou com token inválido recebem 401/403."""
    # Sem header
    response = client.get("/api/v1/health")
    assert response.status_code in (401, 403)

    # Token inválido
    headers = {"Authorization": "Bearer wrong_token"}
    response = client.get("/api/v1/health", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_health_endpoint():
    """Valida o endpoint /api/v1/health com autenticação válida."""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = client.get("/api/v1/health", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "healthy" in data
    assert "backends" in data


def test_query_endpoint():
    """Valida o endpoint /api/v1/query."""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {"query": "teste de busca da API"}
    response = client.post("/api/v1/query", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "observations" in data or "nodes" in data or "edges" in data


def test_decision_endpoint():
    """Valida gravação de decisão pelo endpoint /api/v1/decision (em DRY_RUN)."""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {
        "title": "Decisão via API",
        "content": "Esta decisão foi salva através do endpoint REST da API de nuvem."
    }
    response = client.post("/api/v1/decision", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["saved"] is True
    assert "dry-run" in data["path"]


def test_learning_endpoint():
    """Valida gravação de aprendizado pelo endpoint /api/v1/learning (em DRY_RUN)."""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {
        "title": "Aprendizado via API",
        "content": "Novo padrão identificado no fluxo de testes de integração da API REST."
    }
    response = client.post("/api/v1/learning", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["saved"] is True
    assert "dry-run" in data["path"]


def test_session_end_endpoint():
    """Valida o fechamento de sessão pelo endpoint /api/v1/session-end."""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {
        "summary": "Resumo de teste da API",
        "decisions": ["/path/to/decision1.md"],
        "learnings": ["/path/to/learning1.md"]
    }
    response = client.post("/api/v1/session-end", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["updated"] is True


def test_cloud_routing_e2e():
    """Valida o ciclo completo local -> HTTP -> Cloud API -> local (com servidor em thread de background)."""
    # 1. Inicia o servidor FastAPI em background
    server = BackgroundServer(app, host="127.0.0.1", port=8001)
    server.start()
    time.sleep(0.5)  # Aguarda inicialização

    # 2. Configura o plugin para usar o redirecionamento cloud
    orig_config = dict(api_mod.sm._config)
    orig_dry_run = api_mod.sm.DRY_RUN

    # Configuração temporária apontando para o servidor local mockado em background
    api_mod.sm._config["cloud"] = {
        "enabled": True,
        "url": "http://127.0.0.1:8001",
        "api_key": API_KEY,
    }
    # Servidor remoto em background e cliente têm DRY_RUN=True, então não gravará nada real!


    try:
        # A chamada de busca local deve passar pelo redirecionamento HTTP e retornar do servidor em background
        res = api_mod.sm._query_vault_knowledge("busca teste via rede")
        assert res is not None
        assert "observations" in res or "nodes" in res or "edges" in res


        # A gravação de decisão local deve ser delegada via HTTP para a API de nuvem (que roda em DRY_RUN)
        dec_path = api_mod.sm._save_decision("Decisão Remota", "Conteúdo remoto via rede")
        assert dec_path is not None
        assert "dry-run" in dec_path

        # O fechamento de sessão deve ir via rede
        # Passando listas vazias que são serializadas
        api_mod.sm._update_current_state([], [], "Sessão remota via rede")

    finally:
        # Restaura a configuração e para o servidor
        api_mod.sm._config.clear()
        api_mod.sm._config.update(orig_config)
        api_mod.sm.DRY_RUN = orig_dry_run
        server.stop()
        server.join(timeout=2)
