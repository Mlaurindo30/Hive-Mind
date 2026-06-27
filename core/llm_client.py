"""
Hive-Mind — Cliente LLM unificado (multi-provedor, multi-papel)

Chamada estruturada (JSON Schema + validação Pydantic) com classificação de
erros e fallback explícito por papel (ver core.auth.get_role_config).

Classificação de erros:
  - "validation": saída inválida (Pydantic) — problema de QUALIDADE.
    Retry no MESMO modelo; NUNCA dispara fallback.
  - "auth": 401/402/403, saldo/quota insuficiente, credenciais ausentes —
    problema PERMANENTE. Sem retry no mesmo modelo; fallback direto.
  - "transient": timeout, erro de conexão, 429, 5xx — problema TEMPORÁRIO.
    Retry com backoff; se persistir, fallback.
"""

import os
import sys
import json
import re
import time
import base64
from pathlib import Path
from typing import Any, Optional

import requests

from core.auth import get_credentials, refresh_oauth_token, get_role_config


class LLMValidationError(Exception):
    """Saída da LLM não passou na validação Pydantic (qualidade, não disponibilidade)."""


class LLMChainFailure(RuntimeError):
    """Falha completa da cadeia primário → fallback.

    Preserva tanto a exceção do alvo primário quanto a do fallback (se
    houver), junto com a lista de alvos tentados, para que a quarentena
    e o chamador possam classificar e logar a causa raiz corretamente.

    Atributos:
      chain: lista de tuplas (provider, model) tentadas, na ordem.
      primary_exc: exceção do primário (pode ser None em cadeias de 1 só).
      fallback_exc: exceção do fallback (None se não chegou a tentar).
    """

    def __init__(self, chain, primary_exc, fallback_exc):
        self.chain = list(chain)
        self.primary_exc = primary_exc
        self.fallback_exc = fallback_exc
        msg = f"LLM chain failed (len={len(self.chain)})."
        if self.chain:
            head = self.chain[0]
            msg += f" Primary ({head[0]}/{head[1]}): {primary_exc!r}"
        if len(self.chain) > 1 and fallback_exc is not None:
            tail = self.chain[-1]
            msg += f" | Fallback ({tail[0]}/{tail[1]}): {fallback_exc!r}"
        super().__init__(msg)


# Frases específicas — substrings genéricas ("oauth", "credenciais", "401")
# classificavam como auth qualquer erro que as mencionasse, pulando retries
# de transitórios. Códigos HTTP são tratados via regex com word-boundary.
_AUTH_MARKERS = (
    "unauthorized", "forbidden", "payment required",
    "invalid api key", "invalid_api_key", "api key not valid",
    "insufficient balance", "insufficient credits", "insufficient quota",
    "insufficient_quota", "exceeded your current quota", "saldo insuficiente",
    "credenciais não encontradas", "credenciais inválidas",
    "token expirado", "oauth token expired", "authentication failed",
)
_TRANSIENT_MARKERS = (
    "timeout", "timed out", "connection", "429", "too many requests",
    "rate limit", "service unavailable", "bad gateway", "gateway timeout",
    "server error", "overloaded", "internal error",
)

# MIME types suportados para image_url no padrão OpenAI Vision.
_IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _detect_image_mime(image_path: str) -> str:
    """Detecta o MIME type de um arquivo de imagem pela extensão.

    Usado pelo fallback de imagem (PATCH 1) para construir o data URL
    esperado pelo OpenAI Vision. Caso a extensão seja desconhecida,
    retorna ``image/png`` como default seguro (paridade com o branch
    Google, que também assume png).
    """
    ext = Path(image_path).suffix.lower()
    return _IMAGE_MIME_BY_EXT.get(ext, "image/png")


def classify_llm_error(exc: Exception) -> str:
    """Classifica uma exceção de chamada LLM em 'validation' | 'auth' | 'transient'."""
    if isinstance(exc, LLMValidationError):
        return "validation"
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return "transient"
    msg = str(exc).lower()
    if "pydantic" in msg or "valida" in msg or "validation" in msg:
        return "validation"
    m = re.search(r"api error \((\d{3})\)", msg)
    if m:
        code = int(m.group(1))
        if code in (401, 402, 403):
            return "auth"
        if code == 429 or code >= 500:
            return "transient"
    # Códigos HTTP fora do formato "api error (NNN)" — word-boundary evita
    # falsos positivos (ex.: "403" dentro de "1403" ou de um nome de modelo)
    if re.search(r"\b40[123]\b", msg):
        return "auth"
    if re.search(r"\b(429|5\d{2})\b", msg):
        return "transient"
    if any(s in msg for s in _AUTH_MARKERS):
        return "auth"
    if any(s in msg for s in _TRANSIENT_MARKERS):
        return "transient"
    # Desconhecido: trata como transitório (paridade com o retry genérico anterior)
    return "transient"


def call_llm_structured(prompt: str, system_prompt: str, response_model: Any,
                        image_path: Optional[str] = None,
                        provider: Optional[str] = None,
                        model: Optional[str] = None) -> Any:
    """Chama a LLM e força o retorno no formato Pydantic usando JSON Schema.

    Suporta imagem opcional. Se provider/model não forem informados, usa o
    papel Dreamer (HIVE_DREAMER_PROVIDER/MODEL). Chaves de API são sempre
    resolvidas via PROVIDERS_CONFIG pelo nome do provedor.
    """
    provider = provider or os.environ.get("HIVE_DREAMER_PROVIDER")
    model = model or os.environ.get("HIVE_DREAMER_MODEL")

    # Provider 'gemini-cli': usa o OAuth do Gemini CLI via Code Assist (cloudcode-pa),
    # quota "Unlimited". Credenciais vêm de ~/.gemini (não de env) → tratado aqui,
    # antes do get_credentials padrão. Participa do fallback do papel normalmente.
    if provider in ("gemini-cli", "code-assist"):
        from core.gemini_cli_client import call_gemini_cli_structured
        return call_gemini_cli_structured(prompt, system_prompt, response_model, model,
                                          image_path, provider=provider)

    # Provider 'antigravity': catálogo rico (gemini-3.5-flash, gemini-3.1-pro,
    # claude-*, gpt-oss) via shell-out ao binário `agy` em HOME isolado (sem skills).
    # Credenciais vêm de ~/.gemini (não de env). Participa do fallback do papel.
    if provider == "antigravity":
        from core.agy_client import call_agy_structured
        return call_agy_structured(prompt, system_prompt, response_model, model,
                                   image_path, provider=provider)

    creds = get_credentials(provider)
    if not creds:
        raise Exception(f"Credenciais para '{provider}' não encontradas.")

    schema = response_model.model_json_schema()

    def _do_request(auth_creds):
        if provider in ("google", "gemini"):
            url = f"{auth_creds['url']}/models/{model}:generateContent"
            headers = {"Authorization": f"Bearer {auth_creds['key']}"} if auth_creds['type'] == "oauth" else {}
            if auth_creds['type'] != "oauth":
                url += f"?key={auth_creds['key']}"

            parts = [{"text": f"{system_prompt}\n\n{prompt}"}]
            if image_path:
                with open(image_path, "rb") as image_file:
                    image_data = base64.b64encode(image_file.read()).decode('utf-8')
                    parts.append({
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": image_data
                        }
                    })

            # Gemini JSON Schema format
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                    "responseSchema": schema
                }
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code in [401, 403] and auth_creds['type'] == "oauth":
                return None
            return resp

        else:  # OpenAI-compatible
            url = f"{auth_creds['url']}/chat/completions"
            headers = {"Authorization": f"Bearer {auth_creds['key']}"} if auth_creds['type'] != "local" else {}
            if provider == "openai" and auth_creds['type'] == "oauth":
                headers["originator"] = "openclaw"

            # Conteúdo da mensagem do usuário: string (texto puro) OU lista
            # (texto + imagem, no formato OpenAI Vision). Antes, image_path
            # era silenciosamente descartado no branch OpenAI-compatible —
            # ver PATCH 1 do LLM Council. Imagens só são enviadas quando o
            # caller realmente passa image_path.
            user_content: Any = prompt
            if image_path:
                _mime = _detect_image_mime(image_path)
                with open(image_path, "rb") as _img:
                    _b64 = base64.b64encode(_img.read()).decode("utf-8")
                user_content = [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{_mime};base64,{_b64}"},
                    },
                ]

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.1,
                # Explícito: gateways como o OmniRoute fazem streaming por default quando
                # `stream` é omitido — e nós parseamos JSON único (resp.json()). Forçar false.
                "stream": False,
                # OpenAI Structured Outputs Format
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": schema,
                        "strict": True
                    }
                }
            }
            # Se for provedor local que não suporta 'strict' do OpenAI. OmniRoute roteia
            # p/ 226 backends heterogêneos → usa json_object (schema no prompt) p/ máxima
            # compatibilidade em vez de json_schema strict.
            if auth_creds['type'] == "local" or provider in ["anthropic", "openrouter", "deepseek", "omniroute"]:
                payload["response_format"] = {"type": "json_object"}
                payload["messages"][0]["content"] += f"\n\nOUTPUT MUST MATCH THIS JSON SCHEMA EXACTLY:\n{json.dumps(schema)}"

            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            if resp.status_code in [401, 403] and auth_creds['type'] == "oauth":
                return None
            return resp

    response = _do_request(creds)
    if response is None:
        new_token = refresh_oauth_token(provider)
        if new_token:
            creds['key'] = new_token
            response = _do_request(creds)
        else:
            raise Exception("Falha ao renovar token OAuth.")

    if response is None:
        # Renovação OAuth não devolveu novo token, ou _do_request persistiu
        # em retornar None após 401/403. Sinaliza falha explícita (em vez de
        # crashar em ``response.ok`` abaixo) para que o chamador classifique
        # o erro corretamente.
        raise Exception(
            f"Falha persistente em {provider}: OAuth refresh não recuperou "
            f"o acesso (modelo={model!r})"
        )

    if not response.ok:
        raise Exception(f"API Error ({response.status_code}): {response.text}")

    # Parse e Validação Pydantic
    raw_text = ""
    try:
        if provider in ("google", "gemini"):
            raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            raw_text = response.json()['choices'][0]['message']['content']

        # Clean potential markdown wrappers
        match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
        if match:
            raw_text = match.group(1)

        # Bug 7 fix: o shim OpenAI-compat do Ollama local para modelos que
        # "pensam" (gemma4, qwen3.5) pode devolver content="" e colocar a
        # resposta em ``reasoning``. Sem este fallback, o parser Pydantic
        # aceita "" como válido (ex.: ``description: str`` aceita string vazia)
        # e o resultado fica silenciosamente errado. Detectado com imagem
        # real (PNG 128x128 vermelho) em Ollama /v1 — via /api/chat nativo a
        # resposta ia em ``message.content`` corretamente.
        if not raw_text.strip():
            _resp_json = response.json()
            _msg = _resp_json.get('choices', [{}])[0].get('message', {})
            _reasoning = _msg.get('reasoning') or _msg.get('reasoning_content')
            if _reasoning and _reasoning.strip():
                raw_text = _reasoning

        return response_model.model_validate_json(raw_text.strip())
    except Exception as e:
        raise LLMValidationError(
            f"Falha de validação Pydantic no retorno da LLM: {e}\nTexto Bruto: {raw_text[:200]}"
        )


def call_llm_with_fallback(role: str, prompt: str, system_prompt: str, response_model: Any,
                           image_path: Optional[str] = None,
                           max_retries: int = 2) -> Any:
    """Chamada estruturada com política de retry/fallback do papel *role*.

    - transitório: até *max_retries* retries com backoff no mesmo modelo →
      depois tenta o fallback do papel (se definido);
    - auth/saldo: sem retry no mesmo modelo → fallback direto (com warning);
    - validação Pydantic: até *max_retries* retries no MESMO modelo →
      re-levanta; NUNCA dispara fallback.

    Levanta a última exceção se todos os alvos falharem (o chamador decide
    quarentena/log).
    """
    cfg = get_role_config(role)
    if not cfg:
        raise RuntimeError(
            f"Nenhum LLM configurado para o papel '{role}' "
            f"(defina HIVE_{role.upper()}_PROVIDER/MODEL ou HIVE_DREAMER_PROVIDER/MODEL)."
        )
    targets = [(cfg["provider"], cfg["model"])]
    if cfg.get("fallback_provider") and cfg.get("fallback_model"):
        targets.append((cfg["fallback_provider"], cfg["fallback_model"]))
    # 2º fallback (rede final, ex.: OmniRoute com 226 providers internos).
    if cfg.get("fallback2_provider") and cfg.get("fallback2_model"):
        targets.append((cfg["fallback2_provider"], cfg["fallback2_model"]))

    # Preservamos a primeira exceção vista por alvo para diagnóstico
    # (a do fallback pode ser diferente da do primário — ex.: transient
    # no primário seguido de auth no fallback). Sem isso, a quarentena
    # pode classificar uma tempestade transient que terminou em auth.
    primary_exc: Optional[Exception] = None
    fallback_exc: Optional[Exception] = None
    for idx, (prov, mod) in enumerate(targets):
        if idx > 0:
            print(f"  [Fallback] Papel '{role}': alternando de "
                  f"{targets[0][0]}/{targets[0][1]} para {prov}/{mod}")
        attempt = 0
        while True:
            attempt += 1
            try:
                return call_llm_structured(prompt, system_prompt, response_model,
                                           image_path=image_path, provider=prov, model=mod)
            except Exception as e:
                if idx == 0 and primary_exc is None:
                    primary_exc = e
                elif idx >= 1 and fallback_exc is None:
                    fallback_exc = e
                kind = classify_llm_error(e)
                if kind == "validation":
                    # Qualidade, não disponibilidade: retry no mesmo modelo, nunca fallback
                    if attempt <= max_retries:
                        continue
                    raise
                if kind == "auth":
                    print(f"  [Aviso] Falha de auth/saldo em {prov}/{mod} "
                          f"(papel '{role}'): {e}", file=sys.stderr)
                    break  # sem retry no mesmo modelo: próximo alvo (fallback)
                # Transitório: retry com backoff exponencial
                if attempt <= max_retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                break  # esgotou retries: próximo alvo (fallback)
    # Cadeia inteira falhou: levanta LLMChainFailure preservando ambos os
    # erros e a rota tentada. O chamador (quarentena, dream_cycle) decide
    # o que fazer com base nos atributos primary_exc / fallback_exc.
    raise LLMChainFailure(
        chain=targets,
        primary_exc=primary_exc,
        fallback_exc=fallback_exc,
    )
