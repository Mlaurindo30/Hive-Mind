import os
import sys
import json
import requests
import time
import socket
import webbrowser
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Path do .env local do projeto Hive-Mind
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

def _env(key: str, default: str = "") -> str:
    """Lê uma variável do ambiente, com fallback para o .env do projeto."""
    val = os.environ.get(key)
    if val:
        return val
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, _, v = line.partition("=")
                        if k == key and v:
                            return v
        except OSError:
            pass
    return default

# Registro Mestre de Provedores — Independente e Abrangente
PROVIDERS_CONFIG = {
    "google": {
        "env_var": "GOOGLE_API_KEY",
        "alt_env_var": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "auth_type": ["api_key", "oauth"],
        "doc": "https://aistudio.google.com/app/apikey",
        "oauth": {
            "type": "loopback",
            # Segredos nunca hardcoded: lidos do ambiente ou do .env do projeto
            "client_id": _env("GOOGLE_OAUTH_CLIENT_ID"),
            "client_secret": _env("GOOGLE_OAUTH_CLIENT_SECRET"),
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "redirect_port": 8085,
            "scopes": "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile"
        }
    },
    "openai": {
        "env_var": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "auth_type": ["oauth", "api_key"],
        "doc": "https://platform.openai.com/api-keys",
        "oauth": {
            "type": "custom_openai",
            "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
            "device_code_url": "https://auth.openai.com/api/accounts/deviceauth/usercode",
            "token_url": "https://auth.openai.com/api/accounts/deviceauth/token",
            "exchange_url": "https://auth.openai.com/oauth/token",
            "callback_url": "https://auth.openai.com/deviceauth/callback",
            "headers": {
                "originator": "openclaw",
                "User-Agent": "openclaw/2026.5.27",
                "Content-Type": "application/json"
            }
        }
    },
    "huggingface": {
        "env_var": "HF_TOKEN",
        "base_url": "https://api-inference.huggingface.co/models",
        "auth_type": ["api_key"],
        "doc": "https://huggingface.co/settings/tokens"
    },
    "qwen": {
        "env_var": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "auth_type": ["api_key"],
        "doc": "https://dashscope.console.aliyun.com/apiKey"
    },
    "deepseek": {
        "env_var": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "auth_type": ["api_key"],
        "doc": "https://platform.deepseek.com/"
    },
    "nvidia": {
        "env_var": "NVIDIA_API_KEY",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "auth_type": ["api_key"],
        "doc": "https://build.nvidia.com/"
    },
    "anthropic": {
        "env_var": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1",
        "auth_type": ["api_key"],
        "doc": "https://console.anthropic.com/"
    },
    "openrouter": {
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "auth_type": ["api_key"],
        "doc": "https://openrouter.ai/keys"
    },
    "ollama-cloud": {
        "env_var": "OLLAMA_API_KEY",
        "base_url": "https://ollama.com/v1",
        "auth_type": ["api_key"],
        "doc": "https://ollama.com/"
    },
    "lmstudio": {
        "env_var": "LM_API_KEY",
        "base_url": "http://127.0.0.1:1234/v1",
        "auth_type": ["local"],
        "doc": "LM Studio Local"
    },
    "ollama": {
        "env_var": "OLLAMA_LOCAL",
        "base_url": "http://localhost:11434",
        "auth_type": ["local"],
        "doc": "Ollama Local"
    }
}

# --- Sistema de Loopback Server ---
class OAuthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        query = parse_qs(urlparse(self.path).query)
        code = query.get('code', [None])[0]
        if code:
            self.server.auth_code = code
            self.wfile.write("<h1>Sucesso!</h1><p>Autorizado. Volte ao terminal.</p>".encode())
        else:
            self.wfile.write("<h1>Erro!</h1><p>Código não recebido.</p>".encode())

def start_loopback_server(port):
    server = HTTPServer(('localhost', port), OAuthHandler)
    server.auth_code = None
    thread = threading.Thread(target=server.handle_request)
    thread.daemon = True
    thread.start()
    return server

# --- Funções Core ---
def load_env():
    if not ENV_FILE.exists(): return {}
    vars = {}
    try:
        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2: vars[parts[0]] = parts[1]
    except OSError: pass
    return vars

def save_env(key: str, value: str):
    lines = []
    found = False
    if ENV_FILE.exists():
        with open(ENV_FILE, "r") as f: lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        if lines and not lines[-1].endswith("\n"): lines.append("\n")
        lines.append(f"{key}={value}\n")
    with open(ENV_FILE, "w") as f: f.writelines(lines)

def get_oauth_credentials(provider_name: str):
    cfg = PROVIDERS_CONFIG.get(provider_name)
    if not cfg or "oauth" not in cfg: return None
    oauth = cfg["oauth"]
    if oauth.get("type") == "loopback":
        if provider_name == "google" and (not oauth.get("client_id") or not oauth.get("client_secret")):
            return {"error": "GOOGLE_OAUTH_CLIENT_ID/GOOGLE_OAUTH_CLIENT_SECRET não configurados no .env"}
        port = oauth["redirect_port"]
        server = start_loopback_server(port)
        auth_url = (f"{oauth['auth_url']}?client_id={oauth['client_id']}"
                    f"&redirect_uri=http://localhost:{port}/oauth2callback&response_type=code"
                    f"&scope={oauth['scopes']}&access_type=offline&prompt=consent")
        return {"type": "loopback", "auth_url": auth_url, "server": server}
    elif oauth.get("type") == "custom_openai":
        resp = requests.post(oauth["device_code_url"], json={"client_id": oauth["client_id"]}, headers=oauth["headers"])
        if resp.ok:
            data = resp.json()
            data["verification_url"] = "https://auth.openai.com/codex/device"
            return data
    return {"error": "Iniciação falhou"}

def poll_oauth_token(provider_name: str, init_data: Any):
    cfg = PROVIDERS_CONFIG.get(provider_name)
    oauth = cfg["oauth"]
    if oauth.get("type") == "loopback":
        server = init_data["server"]
        deadline = time.time() + 300
        while server.auth_code is None:
            if time.time() >= deadline:
                return {"error": "Timeout aguardando autorização OAuth (300s)"}
            time.sleep(1)
        payload = {
            "client_id": oauth["client_id"], "client_secret": oauth["client_secret"],
            "code": server.auth_code, "grant_type": "authorization_code",
            "redirect_uri": f"http://localhost:{oauth['redirect_port']}/oauth2callback"
        }
        resp = requests.post(oauth["token_url"], data=payload)
        if resp.ok:
            data = resp.json()
            save_env(f"{provider_name.upper()}_ACCESS_TOKEN", data["access_token"])
            if "refresh_token" in data: save_env(f"{provider_name.upper()}_REFRESH_TOKEN", data["refresh_token"])
            return data
        return {"error": resp.text}
    elif oauth.get("type") == "custom_openai":
        device_auth_id = init_data["device_auth_id"]
        user_code = init_data["user_code"]
        deadline = time.time() + 300
        while True:
            if time.time() >= deadline:
                return {"error": "Timeout no device flow (300s)"}
            payload = {"device_auth_id": device_auth_id, "user_code": user_code}
            resp = requests.post(oauth["token_url"], json=payload, headers=oauth["headers"])
            data = resp.json()
            if resp.ok:
                auth_code = data.get("authorization_code")
                verifier = data.get("code_verifier")
                exch_payload = {
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": oauth["callback_url"],
                    "client_id": oauth["client_id"],
                    "code_verifier": verifier
                }
                headers = oauth["headers"].copy()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                resp_final = requests.post(oauth["exchange_url"], data=exch_payload, headers=headers)
                if resp_final.ok:
                    data_final = resp_final.json()
                    save_env(f"{provider_name.upper()}_ACCESS_TOKEN", data_final["access_token"])
                    if "refresh_token" in data_final: save_env(f"{provider_name.upper()}_REFRESH_TOKEN", data_final["refresh_token"])
                    return data_final
                return {"error": resp_final.text}
            
            if resp.status_code in [400, 403, 404]:
                err_code = data.get("error", {}).get("code") if isinstance(data.get("error"), dict) else data.get("code")
                if "pending" in str(data).lower() or err_code == "deviceauth_authorization_pending":
                    time.sleep(5)
                    continue
            return {"error": data}

def refresh_oauth_token(provider_name: str):
    cfg = PROVIDERS_CONFIG.get(provider_name)
    if not cfg or "oauth" not in cfg: return None
    env = load_env()
    refresh_token = env.get(f"{provider_name.upper()}_REFRESH_TOKEN")
    if not refresh_token: return None
    oauth = cfg["oauth"]
    payload = {"client_id": oauth["client_id"], "refresh_token": refresh_token, "grant_type": "refresh_token"}
    if "client_secret" in oauth: payload["client_secret"] = oauth["client_secret"]
    headers = oauth.get("headers", {}) if oauth.get("type") == "custom_openai" else {}
    if oauth.get("type") == "custom_openai":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        resp = requests.post(oauth["exchange_url"], data=payload, headers=headers)
    else:
        resp = requests.post(oauth["token_url"], data=payload)
    if resp.ok:
        data = resp.json()
        save_env(f"{provider_name.upper()}_ACCESS_TOKEN", data["access_token"])
        return data["access_token"]
    return None

def get_credentials(provider_name: str, prefer_oauth: bool = True) -> Optional[Dict[str, Any]]:
    cfg = PROVIDERS_CONFIG.get(provider_name)
    if not cfg: return None
    env = load_env()
    
    if prefer_oauth and "oauth" in cfg["auth_type"]:
        token = env.get(f"{provider_name.upper()}_ACCESS_TOKEN")
        if token: return {"key": token, "url": cfg["base_url"], "type": "oauth"}
        new_token = refresh_oauth_token(provider_name)
        if new_token: return {"key": new_token, "url": cfg["base_url"], "type": "oauth"}
    
    key = env.get(cfg["env_var"]) or env.get(cfg.get("alt_env_var", ""))
    if key: return {"key": key, "url": cfg["base_url"], "type": "api_key"}
    
    if not prefer_oauth and "oauth" in cfg["auth_type"]:
        token = env.get(f"{provider_name.upper()}_ACCESS_TOKEN")
        if token: return {"key": token, "url": cfg["base_url"], "type": "oauth"}

    if "local" in cfg["auth_type"]: return {"key": "local", "url": cfg["base_url"], "type": "local"}
    return None

def discover_models_realtime():
    """Varre as APIs configuradas e retorna a lista REAL de modelos."""
    all_discovered = []
    for name, cfg in PROVIDERS_CONFIG.items():
        # Google: Tenta API Key primeiro porque o OAuth de redirecionamento bloqueia listagem
        creds_to_try = [get_credentials(name, prefer_oauth=False), get_credentials(name, prefer_oauth=True)] if name == "google" else [get_credentials(name)]
            
        for creds in creds_to_try:
            if not creds: continue
            try:
                if name == "google":
                    # Google API Key sempre retorna a lista completa (50+ modelos)
                    url = f"{creds['url']}/models"
                    headers = {}
                    if creds['type'] == "oauth": headers["Authorization"] = f"Bearer {creds['key']}"
                    else: url += f"?key={creds['key']}"
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.ok:
                        for m in resp.json().get('models', []):
                            if 'generateContent' in m.get('supportedGenerationMethods', []):
                                m_id = m['name'].replace('models/', '')
                                all_discovered.append({"id": m_id, "provider": name, "display": f"[{name}] {m_id}"})
                        break

                elif name == "openai":
                    # Descoberta de Elite: Codex exige injeção e headers de integridade
                    url = f"{creds['url']}/models"
                    headers = {"Authorization": f"Bearer {creds['key']}"}
                    if creds['type'] == "oauth": headers.update(cfg["oauth"].get("headers", {}))
                    resp = requests.get(url, headers=headers, timeout=10)
                    
                    # 1. Tenta listar o que o token permitir
                    if resp.ok:
                        for m in resp.json().get('data', []):
                            all_discovered.append({"id": m['id'], "provider": name, "display": f"[{name}] {m['id']}"})
                    
                    # 2. Injeta os modelos de Elite do Codex mapeados no OpenClaw (opt-in via env)
                    if os.environ.get("HIVE_DREAMER_INJECT_CODEX_ELITES", "").lower() in ("1", "true", "yes"):
                        codex_elites = [
                            "gpt-5.5", "gpt-5.5-pro",
                            "gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini", "gpt-5.4-nano",
                            "gpt-5.3-codex", "gpt-5.3-chat-latest",
                            "gpt-4o", "gpt-4o-mini", "o1-preview", "o1-mini"
                        ]
                        for m_id in codex_elites:
                            all_discovered.append({"id": m_id, "provider": name, "display": f"[{name}] {m_id} (Codex)"})
                    break

                elif name == "ollama":
                    resp = requests.get(f"{creds['url']}/api/tags", timeout=5)
                    if resp.ok:
                        for m in resp.json().get('models', []):
                            all_discovered.append({"id": m['name'], "provider": name, "display": f"[{name}] {m['name']}"})
                        break
                
                elif name in ["anthropic", "huggingface"]:
                    models = ["claude-3-5-sonnet-latest"] if name == "anthropic" else ["meta-llama/Llama-3-8B-Instruct"]
                    for m in models: all_discovered.append({"id": m, "provider": name, "display": f"[{name}] {m}"})
                    break
                
                else:
                    url = f"{creds['url']}/models"
                    headers = {"Authorization": f"Bearer {creds['key']}"} if creds['type'] == "api_key" else {}
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.ok:
                        data = resp.json()
                        items = data.get('data', []) or data.get('models', [])
                        for m in items:
                            m_id = m.get('id') if isinstance(m, dict) else m
                            if m_id: all_discovered.append({"id": m_id, "provider": name, "display": f"[{name}] {m_id}"})
                        break
            except Exception as e:
                print(f"[auth] Falha ao descobrir modelos de {name}: {e}", file=sys.stderr)

    unique = []
    seen = set()
    for m in all_discovered:
        k = f"{m['provider']}:{m['id']}"
        if k not in seen:
            unique.append(m)
            seen.add(k)
    return sorted(unique, key=lambda x: x['display'])
