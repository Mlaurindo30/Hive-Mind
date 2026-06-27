"""
core/gemini_cli_client.py — Provider 'gemini-cli' via Code Assist (cloudcode-pa).

Reaproveita o OAuth do Gemini CLI / Google VS Code extension para falar com o
endpoint **Code Assist** (`cloudcode-pa.googleapis.com/v1internal`), que tem a quota
do tier "Gemini Code Assist" (Unlimited) — MUITO maior que a do AI Studio (API key).

Por que existe: a API generativelanguage (que usávamos) com OAuth dá 403
ACCESS_TOKEN_SCOPE_INSUFFICIENT; com API key tem quota pequena. O Code Assist usa o
MESMO login do CLI e a quota generosa. Validado (2026-06-18): gemini-2.5-flash → 200.

Credenciais do client OAuth: são as do **gemini-cli** (desktop app público, embutidas
no pacote npm aberto) — NÃO são segredos do usuário. Descobertas em runtime no bundle
instalado (sem hardcode no repo). Token/refresh ficam em ~/.gemini (fora do repo).

Sem dependências novas (só requests + stdlib).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

GEMINI_DIR = Path(os.environ.get("GEMINI_CLI_DIR", str(Path.home() / ".gemini")))
LEGACY_CREDS_PATH = GEMINI_DIR / "oauth_creds.json"
GOOGLE_VSCODE_CREDS_PATH = Path.home() / ".cache/google-vscode-extension/auth/credentials.json"
GOOGLE_VSCODE_ADC_PATH = Path.home() / ".cache/google-vscode-extension/auth/application_default_credentials.json"
API_VERSION = "v1internal"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Endpoint Code Assist (cloudcode-pa) — pool estável do Gemini CLI. O antigo pool
# 'antigravity' (daily-cloudcode-pa) só servia gemini-3.1-flash-lite via
# generateContent e foi aposentado: o catálogo rico do antigravity agora vem do
# provider 'antigravity' roteado para core/agy_client.py (CLI nativo).
# GEMINI_CLI_ENDPOINT força um host p/ todos (override).
_ENDPOINTS = {
    "gemini-cli": "https://cloudcode-pa.googleapis.com",
    "code-assist": "https://cloudcode-pa.googleapis.com",
}
DEFAULT_ENDPOINT = "https://cloudcode-pa.googleapis.com"   # gemini-cli (Code Assist estável)
# Compat: alguns lugares/imports antigos referenciam CODE_ASSIST_ENDPOINT.
CODE_ASSIST_ENDPOINT = os.environ.get("GEMINI_CLI_ENDPOINT", DEFAULT_ENDPOINT)

# A cota do 429 é POR MODELO ("exhausted capacity on THIS MODEL"). Logo, quando um
# modelo esgota, tentar OUTRO modelo do mesmo provider (quota independente) resolve
# ANTES de trocar de provider. Ordem: barato/rápido → mais capaz.
# Modelos que a superfície Code Assist (cloudcode-pa, v1internal:generateContent)
# REALMENTE aceita — validado por chamada real em 2026-06-26 (200/429 = existe;
# 404 = não existe), em 2 passagens p/ filtrar transitórios. Ordem: rápido → capaz.
# IMPORTANTE: aqui o Gemini 3.x usa a forma '-preview' (gemini-3.1-pro-preview).
# gemini-3.5-flash e gemini-3.1-pro (sem -preview) dão 404 aqui — esses só via o
# provider 'antigravity' (core/agy_client.py / CLI nativo). Não adicione sem validar.
_GEMINI_CLI_MODELS = [
    "gemini-2.5-flash", "gemini-3.1-flash-lite", "gemini-3-flash-preview",
    "gemini-3.1-pro-preview", "gemini-3-pro-preview", "gemini-2.5-pro",
]
_MODEL_ROTATION = {
    "gemini-cli": _GEMINI_CLI_MODELS,
    "code-assist": _GEMINI_CLI_MODELS,
}


def _model_chain(provider: Optional[str], model: str) -> list:
    """Modelo pedido primeiro, depois os demais do provider (dedup) p/ rotação no 429."""
    rot = _MODEL_ROTATION.get((provider or "").lower(), [])
    return [model] + [m for m in rot if m != model]


def _endpoint_for(provider: Optional[str]) -> str:
    """Host Code Assist do provider (env GEMINI_CLI_ENDPOINT força p/ todos)."""
    override = os.environ.get("GEMINI_CLI_ENDPOINT")
    if override:
        return override
    return _ENDPOINTS.get((provider or "").lower(), DEFAULT_ENDPOINT)


_client_creds_cache: Optional[tuple] = None   # (client_id, client_secret)
_project_cache: dict = {}                      # {endpoint: projectId}


class GeminiCliError(Exception):
    """Erro do provider gemini-cli (mensagem classificável por call_llm_with_fallback)."""


def _bundle_dir() -> Optional[Path]:
    """Localiza o bundle do @google/gemini-cli instalado (p/ extrair client creds)."""
    candidates = [
        Path.home() / ".npm-global/lib/node_modules/@google/gemini-cli/bundle",
        Path("/usr/lib/node_modules/@google/gemini-cli/bundle"),
        Path("/usr/local/lib/node_modules/@google/gemini-cli/bundle"),
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _discover_client_creds() -> tuple:
    """client_id + client_secret do gemini-cli (do bundle instalado). Cacheado.

    São credenciais de app desktop público (não confidenciais); ficam embutidas no
    pacote npm aberto. Não as hardcodamos no nosso repo."""
    global _client_creds_cache
    if _client_creds_cache:
        return _client_creds_cache
    # Permite override por env (operador), senão lê do bundle.
    cid = os.environ.get("GEMINI_CLI_CLIENT_ID")
    csecret = os.environ.get("GEMINI_CLI_CLIENT_SECRET")
    if not (cid and csecret):
        adc_path = GOOGLE_VSCODE_ADC_PATH
        if adc_path.is_file():
            try:
                adc = json.loads(adc_path.read_text())
                cid = cid or adc.get("client_id")
                csecret = csecret or adc.get("client_secret")
            except OSError:
                pass
    if not (cid and csecret):
        bundle = _bundle_dir()
        if not bundle:
            raise GeminiCliError(
                "gemini-cli não instalado: bundle não encontrado p/ refresh do OAuth.")
        # O bundle tem 2 client_ids (gemini-cli e gcloud SDK). O token de
        # ~/.gemini/oauth_creds.json é emitido pelo CLIENT DO GEMINI-CLI — o refresh
        # PRECISA desse par. Varremos todos os .js coletando: (a) o client_id do
        # gemini-cli (prefixo conhecido 681255809395, com fallback p/ qualquer outro
        # que NÃO seja o gcloud 764086051850) e (b) o único secret GOCSPX-*.
        GEMINI_CLI_PREFIX = "681255809395-"
        GCLOUD_PREFIX = "764086051850-"
        found_cli_id = found_other_id = None
        for js in bundle.rglob("*.js"):
            try:
                txt = js.read_text(errors="ignore")
            except OSError:
                continue
            for m in re.finditer(r"(\d+-[a-z0-9]+\.apps\.googleusercontent\.com)", txt):
                val = m.group(1)
                if val.startswith(GEMINI_CLI_PREFIX):
                    found_cli_id = val
                elif not val.startswith(GCLOUD_PREFIX):
                    found_other_id = found_other_id or val
            if not csecret:
                ms = re.search(r"(GOCSPX-[A-Za-z0-9_\-]+)", txt)
                if ms:
                    csecret = ms.group(1)
            if found_cli_id and csecret:
                break
        cid = cid or found_cli_id or found_other_id
    if not (cid and csecret):
        raise GeminiCliError("client_id/secret do gemini-cli não localizados no bundle.")
    _client_creds_cache = (cid, csecret)
    return _client_creds_cache


def _load_creds() -> dict:
    source = None
    raw = None
    for path in (LEGACY_CREDS_PATH, GOOGLE_VSCODE_CREDS_PATH, GOOGLE_VSCODE_ADC_PATH):
        if path.is_file():
            source = path
            raw = json.loads(path.read_text())
            break
    if raw is None or source is None:
        raise GeminiCliError(
            "OAuth do gemini-cli/antigravity ausente — rode `gemini` ou `agy` e faça login.")
    return _normalize_creds(raw, source)


def _normalize_creds(raw: dict, source: Path) -> dict:
    """Normaliza formatos diferentes para access_token/refresh_token/expiry_date."""
    creds = dict(raw)
    creds["_source_path"] = str(source)
    if "accessToken" in creds:
        creds["access_token"] = creds.get("accessToken")
    if "refreshToken" in creds:
        creds["refresh_token"] = creds.get("refreshToken")
    if "accessTokenExpirySecond" in creds:
        try:
            expiry = int(float(creds["accessTokenExpirySecond"]))
            # A extensão Google VS Code usa esse campo como milissegundos,
            # apesar do nome "Second"; alguns formatos antigos usam segundos.
            creds["expiry_date"] = expiry if expiry > 10_000_000_000 else expiry * 1000
        except (TypeError, ValueError):
            pass
    if "expiry" in creds and "expiry_date" not in creds:
        try:
            creds["expiry_date"] = int(float(creds["expiry"]) * 1000)
        except (TypeError, ValueError):
            pass
    return creds


def _save_creds(creds: dict) -> None:
    source = Path(creds.get("_source_path") or LEGACY_CREDS_PATH)
    payload = dict(creds)
    payload.pop("_source_path", None)
    if source == GOOGLE_VSCODE_CREDS_PATH:
        payload["accessToken"] = payload.get("access_token", payload.get("accessToken"))
        payload["refreshToken"] = payload.get("refresh_token", payload.get("refreshToken"))
        if payload.get("expiry_date"):
            payload["accessTokenExpirySecond"] = int(payload["expiry_date"] / 1000)
        for key in ("access_token", "refresh_token", "expiry_date"):
            payload.pop(key, None)
    elif source == GOOGLE_VSCODE_ADC_PATH:
        source = LEGACY_CREDS_PATH
        payload = {
            "access_token": payload.get("access_token"),
            "refresh_token": payload.get("refresh_token"),
            "expiry_date": payload.get("expiry_date"),
        }
    source.write_text(json.dumps(payload))
    try:
        source.chmod(0o600)
    except OSError:
        pass


def _refresh(creds: dict) -> dict:
    """Renova o access_token via refresh_token + client creds do CLI. Persiste."""
    cid, csecret = _discover_client_creds()
    r = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": creds["refresh_token"],
        "client_id": cid,
        "client_secret": csecret,
    }, timeout=30)
    if not r.ok:
        raise GeminiCliError(f"falha no refresh OAuth do gemini-cli: {r.status_code} {r.text[:200]}")
    tok = r.json()
    creds["access_token"] = tok["access_token"]
    creds["expiry_date"] = int((time.time() + tok.get("expires_in", 3600)) * 1000)
    _save_creds(creds)
    return creds


def get_access_token() -> str:
    """access_token válido (renova com folga de 60s se expirado)."""
    creds = _load_creds()
    if creds.get("expiry_date", 0) / 1000.0 <= time.time() + 60:
        creds = _refresh(creds)
    return creds["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_project_id(token: str, endpoint: Optional[str] = None) -> str:
    """projectId do Code Assist via loadCodeAssist. Cacheado POR ENDPOINT (antigravity
    e cloudcode-pa têm projects distintos)."""
    endpoint = endpoint or DEFAULT_ENDPOINT
    if os.environ.get("GEMINI_CLI_PROJECT"):
        return os.environ["GEMINI_CLI_PROJECT"]
    if endpoint in _project_cache:
        return _project_cache[endpoint]
    r = requests.post(f"{endpoint}/{API_VERSION}:loadCodeAssist",
                      headers=_headers(token), json={"metadata": {"pluginType": "GEMINI"}},
                      timeout=30)
    if not r.ok:
        raise GeminiCliError(f"loadCodeAssist falhou ({endpoint}): {r.status_code} {r.text[:200]}")
    proj = r.json().get("cloudaicompanionProject")
    if not proj:
        raise GeminiCliError("loadCodeAssist não devolveu cloudaicompanionProject.")
    _project_cache[endpoint] = proj
    return proj


_SCHEMA_DROP_KEYS = {"$defs", "$schema", "title", "default", "additionalProperties",
                     "discriminator", "examples", "$id", "definitions"}


def _to_gemini_schema(node: Any, defs: Optional[dict] = None) -> Any:
    """Converte o JSON Schema do Pydantic no subset aceito pelo responseSchema do
    Code Assist/Gemini: resolve `$ref`/`$defs` (inline), remove chaves não suportadas
    (`$defs`, `title`, `default`, `additionalProperties`, …) e normaliza `anyOf:[T,null]`
    → `T` + `nullable:true`. Sem isso, schemas aninhados dão 400 'Unknown name $defs'."""
    if defs is None:
        defs = (node or {}).get("$defs") or (node or {}).get("definitions") or {}
    if isinstance(node, list):
        return [_to_gemini_schema(x, defs) for x in node]
    if not isinstance(node, dict):
        return node

    # $ref → inline a definição referenciada (mais chaves irmãs, se houver).
    if "$ref" in node:
        name = node["$ref"].split("/")[-1]
        merged = _to_gemini_schema(dict(defs.get(name, {})), defs)
        for k, v in node.items():
            if k != "$ref":
                merged[k] = _to_gemini_schema(v, defs)
        return merged

    # anyOf/oneOf com [T, null] (Optional do Pydantic) → T + nullable.
    for key in ("anyOf", "oneOf"):
        if key in node:
            variants = [v for v in node[key] if not (isinstance(v, dict) and v.get("type") == "null")]
            has_null = any(isinstance(v, dict) and v.get("type") == "null" for v in node[key])
            if len(variants) == 1:
                merged = _to_gemini_schema(variants[0], defs)
                if has_null:
                    merged["nullable"] = True
                for k, v in node.items():
                    if k not in (key,):
                        merged.setdefault(k, _to_gemini_schema(v, defs))
                return merged

    out: dict = {}
    for k, v in node.items():
        if k in _SCHEMA_DROP_KEYS:
            continue
        out[k] = _to_gemini_schema(v, defs)
    return out


def _extract_text(data: dict) -> str:
    resp = data.get("response", data)
    parts = resp["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def call_gemini_cli_structured(prompt: str, system_prompt: str, response_model: Any,
                               model: str, image_path: Optional[str] = None,
                               provider: Optional[str] = None) -> Any:
    """Chamada estruturada via Code Assist. Retorna instância de response_model.

    `provider` escolhe o endpoint/quota: 'antigravity' (daily-cloudcode-pa) ou
    'gemini-cli'/'code-assist' (cloudcode-pa). Envelope Code Assist
    (`{model, project, request:{contents, generationConfig}}`)."""
    import base64
    endpoint = _endpoint_for(provider)
    token = get_access_token()
    project = get_project_id(token, endpoint)
    # Code Assist não aceita $defs/$ref no responseSchema → inline + saneamento.
    schema = _to_gemini_schema(response_model.model_json_schema())

    parts: list[dict] = [{"text": f"{system_prompt}\n\n{prompt}"}]
    if image_path:
        with open(image_path, "rb") as f:
            parts.append({"inlineData": {"mimeType": "image/png",
                                         "data": base64.b64encode(f.read()).decode("utf-8")}})
    gen_cfg = {"temperature": 0.1, "responseMimeType": "application/json",
               "responseSchema": schema}

    last_429 = None
    for m in _model_chain(provider, model):
        body = {"model": m, "project": project,
                "request": {"contents": [{"role": "user", "parts": parts}],
                            "generationConfig": gen_cfg}}
        r = requests.post(f"{endpoint}/{API_VERSION}:generateContent",
                          headers=_headers(token), json=body, timeout=120)
        if r.status_code in (401, 403):
            # auth/scope — sinaliza p/ o fallback do papel não insistir no mesmo alvo.
            raise GeminiCliError(f"authentication failed (gemini-cli {r.status_code}): {r.text[:200]}")
        if r.status_code == 429:
            # Quota é POR MODELO → tenta o próximo modelo do provider antes de desistir.
            last_429 = r.text[:160]
            continue
        if not r.ok:
            raise GeminiCliError(f"gemini-cli {r.status_code}: {r.text[:200]}")
        return response_model.model_validate_json(_extract_text(r.json()))
    # Todos os modelos do provider esgotados → 429 transient (dispara fallback do papel).
    raise GeminiCliError(f"gemini-cli 429 em todos os modelos do provider: {last_429}")
