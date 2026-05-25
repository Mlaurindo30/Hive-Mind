#!/usr/bin/env python3
"""
Sinapse Agent — Microsserviço REST Cloud API (Fase 4.3).
Expõe endpoints seguros em FastAPI para consulta e gravação remota de memória.
"""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# Inicialização da FastAPI
app = FastAPI(
    title="Sinapse Cloud Memory API",
    description="API REST de nuvem para a camada de memória universal do Sinapse Agent",
    version="1.0.0",
)

security = HTTPBearer()

# ---------------------------------------------------------------------------
# Carregar o plugin sinapse-memory.py dinamicamente
# ---------------------------------------------------------------------------
if "sinapse_memory" not in sys.modules:
    _PLUGIN_PATH = Path(__file__).resolve().parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
    if not _PLUGIN_PATH.exists():
        raise RuntimeError(f"Plugin sinapse-memory.py não encontrado em {_PLUGIN_PATH}")
    spec = importlib.util.spec_from_file_location("sinapse_memory", _PLUGIN_PATH)
    sm = importlib.util.module_from_spec(spec)
    sys.modules["sinapse_memory"] = sm
    spec.loader.exec_module(sm)
else:
    import sinapse_memory as sm
sm.API_SERVER_MODE = True




# ---------------------------------------------------------------------------
# Resolução de API Key
# ---------------------------------------------------------------------------
def get_expected_api_key() -> str:
    """Resolve a API key esperada do ambiente ou do arquivo sinapse.yaml."""
    # 1. Variável de ambiente direta (maior precedência)
    env_key = os.environ.get("SINAPSE_API_KEY")
    if env_key:
        return env_key

    # 2. Configuração do yaml
    cloud_config = sm._config.get("cloud", {}) if hasattr(sm, "_config") else {}
    config_key = cloud_config.get("api_key")
    if config_key:
        # Se for uma variável de ambiente formatada como ${VAR} ou $VAR
        match = re.match(r"^\$?\{?([A-Za-z0-9_]+)\}?$", str(config_key))
        if match:
            var_name = match.group(1)
            resolved = os.environ.get(var_name)
            if resolved:
                return resolved
        return str(config_key)

    # 3. Fallback seguro por padrão caso nada esteja configurado (apenas para testes)
    return "sinapse_default_secret_key"


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Injeção de dependência para autenticar a requisição com Token Bearer."""
    token = credentials.credentials
    expected = get_expected_api_key()
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return token


# ---------------------------------------------------------------------------
# Modelos de Requisição Pydantic
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str


class DecisionRequest(BaseModel):
    title: str
    content: str


class LearningRequest(BaseModel):
    title: str
    content: str


class ZettelkastenRequest(BaseModel):
    source: str
    output_dir: Optional[str] = "cerebro/atoms"


class SessionEndRequest(BaseModel):
    summary: str
    decisions: Optional[List[str]] = []
    learnings: Optional[List[str]] = []


# ---------------------------------------------------------------------------
# Endpoints da API
# ---------------------------------------------------------------------------
@app.get("/api/v1/health", dependencies=[Depends(verify_api_key)])
def get_health():
    """Retorna o estado de saúde de todos os backends da VPS."""
    try:
        return sm.health_check()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}",
        )


@app.post("/api/v1/query", dependencies=[Depends(verify_api_key)])
def post_query(body: QueryRequest):
    """Executa a busca híbrida concorrente em múltiplos backends locais na VPS."""
    try:
        result = sm._query_vault_knowledge(body.query)
        if result is None:
            return {"query": body.query, "observations": [], "nodes": [], "edges": []}
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(e)}",
        )


@app.post("/api/v1/decision", dependencies=[Depends(verify_api_key)])
def post_decision(body: DecisionRequest):
    """Salva uma decisão no vault remoto."""
    try:
        path = sm._save_decision(body.title, body.content)
        if path is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to write decision to vault.",
            )
        return {"saved": True, "path": path}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.post("/api/v1/learning", dependencies=[Depends(verify_api_key)])
def post_learning(body: LearningRequest):
    """Salva um aprendizado no Patterns.md remoto."""
    try:
        path = sm._save_learning(body.title, body.content)
        if path is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to write learning to Patterns.md.",
            )
        return {"saved": True, "path": path}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.post("/api/v1/zettelkasten", dependencies=[Depends(verify_api_key)])
def post_zettelkasten(body: ZettelkastenRequest):
    """Executa o particionamento Zettelkasten em cima de um arquivo no servidor."""
    try:
        zk_script = Path(__file__).resolve().parent / "sinapse-zettelkasten.py"
        if not zk_script.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="sinapse-zettelkasten.py utility not found.",
            )

        spec_zk = importlib.util.spec_from_file_location("sinapse_zettelkasten", zk_script)
        zk_mod = importlib.util.module_from_spec(spec_zk)
        spec_zk.loader.exec_module(zk_mod)

        # Invoca o split
        files = zk_mod.split_monolithic_file(body.source, body.output_dir)
        return {"atoms_created": len(files), "files": files}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.post("/api/v1/session-end", dependencies=[Depends(verify_api_key)])
def post_session_end(body: SessionEndRequest):
    """Consolida o fim da sessão e atualiza o Current State.md remoto."""
    try:
        sm._update_current_state(body.decisions or [], body.learnings or [], body.summary)
        return {"updated": True}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )



if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SINAPSE_API_HOST", "0.0.0.0")
    port = int(os.environ.get("SINAPSE_API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
