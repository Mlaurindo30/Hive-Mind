#!/usr/bin/env python3
"""
Hive-Mind — Local & Cloud REST API (Vault Hardening Phase)
Expõe endpoints seguros para Dashboard, Auto-Link e Sincronização Remota.
Implementa Criptografia Automática de Segredos (Vault) e Rate Limiting.
"""

import importlib.util
import json
import os
import re
import secrets
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Criptografia e Segurança
from cryptography.fernet import Fernet
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Tenta carregar variáveis do .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuração de Segurança (Vault)
# ---------------------------------------------------------------------------

# Padrões Regex para Identificação de Segredos
SECRET_PATTERNS = {
    "openai_project": r"sk-proj-[a-zA-Z0-9_-]{40,}",
    "openai": r"sk-[a-zA-Z0-9]{40,}\b",
    "anthropic": r"sk-ant-api03-[a-zA-Z0-9-]{80,120}",
    "aws": r"AKIA[0-9A-Z]{16}",
    "google": r"AIza[0-9A-Za-z-_]{35}",
    "nvidia": r"nvapi-[a-zA-Z0-9-]{64,128}",
    "slack": r"xoxb-[0-9]{10,13}-[a-zA-Z0-9]{12,24}",
}

def get_master_key():
    """Recupera a chave mestra do .env."""
    key = os.environ.get("HIVE_MIND_MASTER_KEY")
    if not key:
        raise RuntimeError("HIVE_MIND_MASTER_KEY não encontrada no .env!")
    return key.encode()

def encrypt_and_vault(text: str) -> str:
    """
    Identifica segredos no texto, criptografa-os e substitui por referências ao vault.
    Retorna o texto processado (sanitizado).
    """
    if not isinstance(text, str):
        return text
        
    master_key = get_master_key()
    f = Fernet(master_key)
    processed_text = text
    
    try:
        from core.database import get_connection
        conn = get_connection()
        
        for kind, pattern in SECRET_PATTERNS.items():
            matches = re.findall(pattern, processed_text)
            for secret in set(matches): # set para evitar duplicatas no mesmo texto
                secret_id = f"vault-{uuid.uuid4().hex[:8]}"
                encrypted = f.encrypt(secret.encode())
                
                # Salva no banco de dados (tabela vault) utilizando execute_insert para garantir integridade
                execute_insert(conn, "vault", {
                    "id": secret_id,
                    "encrypted_secret": encrypted,
                    "metadata": json.dumps({"kind": kind, "origin": "api-interceptor"})
                })
                
                # Substitui no texto original
                placeholder = f"[VAULT_SECURE:{secret_id}]"
                processed_text = processed_text.replace(secret, placeholder)
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[vault] Erro ao processar segredos: {e}")
        # Em caso de erro crítico no banco, faz o redaction simples por segurança
        for pattern in SECRET_PATTERNS.values():
            processed_text = re.sub(pattern, "[ENCRYPTION_FAILED_REDACTED]", processed_text)
            
    return processed_text

# Inicialização do Rate Limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Hive-Mind Vault API",
    description="Interface com Criptografia de Segredos para o Cérebro de IA",
    version="1.4.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS restrito: origens configuráveis via HIVE_MIND_CORS_ORIGINS (lista separada por vírgula)
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "HIVE_MIND_CORS_ORIGINS", "http://localhost:37700,http://localhost:8000"
    ).split(",")
    if o.strip()
]
# Regra do CORS: wildcard "*" é incompatível com allow_credentials=True
_cors_allow_credentials = "*" not in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# ---------------------------------------------------------------------------
# Carregar o Core
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

try:
    from core.database import get_connection, query_hybrid, execute_insert
except ImportError:
    raise RuntimeError("Core Hive-Mind não encontrado")

def get_expected_api_key() -> str:
    key = os.environ.get("HIVE_MIND_API_KEY")
    if not key:
        raise RuntimeError("HIVE_MIND_API_KEY não configurada — a API não inicia sem chave.")
    return key

def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    # Comparação em tempo constante para evitar timing attacks
    if not secrets.compare_digest(token, get_expected_api_key()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Acesso negado.")
    return token

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
@limiter.limit("60/minute")
def get_health(request: Request):
    return {"status": "online", "engine": "Hive-Mind Vault Ready"}

@app.post("/api/v1/observations", dependencies=[Depends(verify_api_key)])
@limiter.limit("20/minute")
def post_observation(request: Request, body: Any):
    """
    Gravação de observações com CRIPTOGRAFIA AUTOMÁTICA DE SEGREDOS.
    Nota: body é Any para flexibilidade, mas esperamos os campos de ObservationRequest.
    """
    try:
        # Extração manual para lidar com dicionários ou objetos Pydantic
        data = body.dict() if hasattr(body, "dict") else dict(body)
        
        title = data.get("title", "Sem título")
        content = data.get("content", "")
        kind = data.get("kind", "event")
        project = data.get("project")
        session_id = data.get("session_id")
        agent_id = data.get("agent_id", "unknown-agent")
        
        # Hardening: Criptografar segredos e mover para o Vault
        safe_title = encrypt_and_vault(title)
        safe_content = encrypt_and_vault(content)
        
        conn = get_connection()
        execute_insert(conn, "observations", {
            "title": safe_title,
            "content": safe_content,
            "type": kind,
            "project": project,
            "session_id": session_id,
            "metadata": json.dumps({"agent": agent_id, "timestamp": datetime.now().isoformat(), "hardened": True})
        })
        conn.commit()
        conn.close()
        
        vault_count = safe_content.count("[VAULT_SECURE:") + safe_title.count("[VAULT_SECURE:")
        
        return {
            "saved": True, 
            "title": safe_title, 
            "vault_refs": vault_count,
            "status": "hardened" if vault_count > 0 else "clean"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/query", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
def post_query(request: Request, body: Any):
    """Consulta híbrida protegida."""
    try:
        data = body.dict() if hasattr(body, "dict") else dict(body)
        results = query_hybrid(data.get("query", ""), limit=data.get("limit", 5))
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/semantic/related", dependencies=[Depends(verify_api_key)])
def get_related(request: Request, file_path: str = Query(...)):
    # ... (mesma lógica anterior, mantida para compatibilidade Obsidian)
    try:
        conn = get_connection()
        row = conn.execute("SELECT id FROM neurons WHERE source_file = ? OR id = ?", 
                           (file_path, file_path.replace("/", "_").replace(".md", ""))).fetchone()
        if not row:
            conn.close()
            return {"results": []}
        neuron_id = row['id']
        vec_row = conn.execute("SELECT embedding FROM search_vec WHERE neuron_id = ?", (neuron_id,)).fetchone()
        if not vec_row:
            conn.close()
            return {"results": []}
        related = conn.execute("""
            SELECT n.label, v.distance FROM search_vec v JOIN neurons n ON v.neuron_id = n.id
            WHERE v.embedding MATCH ? AND v.k = 6 ORDER BY v.distance ASC
        """, (vec_row['embedding'],)).fetchall()
        results = []
        for r in related:
            if r['label'].lower() == os.path.basename(file_path).replace(".md", "").lower(): continue
            affinity = max(0, min(100, int((1 - r['distance']) * 100)))
            results.append({"label": r['label'], "affinity": f"{affinity}%"})
        conn.close()
        return {"results": results[:5]}
    except Exception:
        return {"results": []}

@app.get("/api/v1/vault/{secret_id}", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
def get_vault_secret(request: Request, secret_id: str):
    """
    Recupera e descriptografa um segredo do vault pela referência
    [VAULT_SECURE:<id>]. Requer HIVE_MIND_MASTER_KEY e Bearer token.
    Rate limit agressivo: endpoint sensível.
    """
    if not re.fullmatch(r"vault-[a-f0-9]{8}", secret_id):
        raise HTTPException(status_code=400, detail="ID de vault inválido.")
    try:
        f = Fernet(get_master_key())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT encrypted_secret, metadata FROM vault WHERE id = ?", (secret_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Segredo não encontrado no vault.")
        try:
            secret = f.decrypt(row["encrypted_secret"]).decode()
        except Exception:
            raise HTTPException(status_code=500, detail="Falha ao descriptografar (master key incorreta?).")
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        return {"id": secret_id, "secret": secret, "kind": meta.get("kind")}
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    # Fail-closed: valida a chave de API antes de subir o servidor
    get_expected_api_key()
    host = os.environ.get("HIVE_MIND_API_HOST", "0.0.0.0")
    port = int(os.environ.get("HIVE_MIND_API_PORT", "37702"))
    uvicorn.run(app, host=host, port=port)
