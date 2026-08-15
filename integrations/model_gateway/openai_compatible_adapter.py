"""
integrations/model_gateway/openai_compatible_adapter.py — Adapter for any
backend exposing the OpenAI /v1 HTTP surface: LM Studio, llama.cpp server,
vLLM, SGLang, and generic openai_compatible endpoints all reuse this single
class (provider identity comes from ModelProfile.provider / the constructor
arg, not from a subclass per backend). See specs/model-gateway.md
Requirement 15.
"""
from __future__ import annotations

import base64
import json
import sys
from typing import Optional
from urllib.parse import urlparse

import requests

from integrations.model_gateway.base import BaseModelAdapter

# Basic SSRF guard (specs/model-gateway.md § Out of Scope: "basic checks
# ... are required"; DNS-rebinding protection for a remote host masquerading
# as localhost is explicitly NOT covered — see docs/14-model-gateway.md
# "Known limitations").
_BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data"}
_BLOCKED_HOSTS = {
    "169.254.169.254",       # AWS/GCP/Azure metadata IP
    "metadata.google.internal",
    "fd00:ec2::254",         # AWS IMDSv2 IPv6
}


def _reject_unsafe_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"blocked endpoint scheme {parsed.scheme!r} (only http/https allowed)")
    host = (parsed.hostname or "").lower()
    if host in _BLOCKED_HOSTS:
        raise ValueError(f"blocked endpoint host {host!r} (cloud metadata address)")
    if host == "0.0.0.0":
        print(f"[model_gateway] WARNING: endpoint host is 0.0.0.0 ({endpoint}) — "
              f"this binds to all interfaces, not just local", file=sys.stderr)


class OpenAICompatibleAdapter(BaseModelAdapter):
    def __init__(self, provider: str = "openai_compatible"):
        self.provider = provider

    def _headers(self, profile) -> dict:
        headers = {"Content-Type": "application/json"}
        api_key = profile.api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _base_url(self, profile) -> str:
        endpoint = (profile.endpoint or "").rstrip("/")
        if not endpoint:
            raise ValueError(f"model {profile.id!r} has no endpoint configured")
        _reject_unsafe_endpoint(endpoint)
        return endpoint

    def _post(self, profile, path: str, payload: dict, timeout_s: float):
        """Returns (data, error). Exactly one is non-None."""
        try:
            url = f"{self._base_url(profile)}{path}"
        except ValueError as exc:
            return None, f"invalid_endpoint:{exc}"
        try:
            resp = requests.post(url, headers=self._headers(profile), json=payload, timeout=timeout_s)
        except requests.exceptions.Timeout:
            return None, "timeout"
        except requests.exceptions.ConnectionError:
            return None, "connection_refused"
        except requests.exceptions.RequestException as exc:
            return None, f"request_error:{exc}"

        if resp.status_code in (401, 403):
            return None, "auth_error"
        if resp.status_code == 429:
            return None, "rate_limited"
        if resp.status_code >= 500:
            return None, f"backend_error:{resp.status_code}"
        if resp.status_code >= 400:
            return None, f"client_error:{resp.status_code}"

        content_type = resp.headers.get("content-type", "")
        if "application/json" not in content_type:
            return None, "malformed_response:non_json_content_type"
        try:
            return resp.json(), None
        except (ValueError, json.JSONDecodeError):
            return None, "malformed_response:invalid_json"

    def _clamped_max_tokens(self, profile, requested: Optional[int]) -> tuple[int, bool]:
        if requested is None:
            return profile.max_output_tokens, False
        if requested > profile.max_output_tokens:
            return profile.max_output_tokens, True
        return requested, False

    def chat(self, profile, messages, temperature=None, max_tokens=None, timeout_s=60, **_):
        from core.model_gateway import ModelResponse
        effective_max, clamped = self._clamped_max_tokens(profile, max_tokens)
        payload = {
            "model": profile.model,
            "messages": messages,
            "temperature": 0.2 if temperature is None else temperature,
            "max_tokens": effective_max,
        }
        if profile.capabilities.tool_calling:
            pass  # tools are passed by the caller via messages/kwargs in a future iteration
        data, err = self._post(profile, "/chat/completions", payload, timeout_s or 60)
        if err:
            return ModelResponse(ok=False, content=None, model_id=profile.id, provider=self.provider,
                                  endpoint=profile.endpoint, latency_ms=0.0, input_tokens=None,
                                  output_tokens=None, cost_estimate=None, fallback_used=False,
                                  fallback_chain=[], error=err)
        choices = data.get("choices")
        if not choices:
            return ModelResponse(ok=False, content=None, model_id=profile.id, provider=self.provider,
                                  endpoint=profile.endpoint, latency_ms=0.0, input_tokens=None,
                                  output_tokens=None, cost_estimate=None, fallback_used=False,
                                  fallback_chain=[], error="malformed_response:no_choices", raw=data)
        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls")
        content = message.get("content") if tool_calls is None else {
            "content": message.get("content"), "tool_calls": tool_calls,
        }
        usage = data.get("usage") or {}
        if clamped:
            data = {**data, "_gateway_clamped_max_tokens": True}
        return ModelResponse(
            ok=True, content=content, model_id=profile.id, provider=self.provider,
            endpoint=profile.endpoint, latency_ms=0.0,
            input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
            cost_estimate=self._estimate_cost(profile, usage.get("prompt_tokens"), usage.get("completion_tokens")),
            fallback_used=False, fallback_chain=[], error=None, raw=data,
        )

    def structured(self, profile, messages, schema, timeout_s=60, image_path=None, **_):
        from core.model_gateway import ModelResponse
        if image_path and profile.legacy_provider == "ollama":
            try:
                with open(image_path, "rb") as image_file:
                    image = base64.b64encode(image_file.read()).decode("ascii")
                endpoint = self._base_url(profile)
                root = endpoint[:-3] if endpoint.endswith("/v1") else endpoint
                system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
                user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
                response = requests.post(f"{root}/api/chat", headers={"Content-Type": "application/json"}, json={"model": profile.model, "stream": False, "format": schema, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user, "images": [image]}]}, timeout=timeout_s or 60)
                if response.status_code >= 400:
                    return ModelResponse(ok=False, content=None, model_id=profile.id, provider=self.provider, endpoint=profile.endpoint, latency_ms=0.0, input_tokens=None, output_tokens=None, cost_estimate=None, fallback_used=False, fallback_chain=[], error=f"client_error:{response.status_code}")
                return ModelResponse(ok=True, content=json.loads(response.json()["message"]["content"]), model_id=profile.id, provider=self.provider, endpoint=profile.endpoint, latency_ms=0.0, input_tokens=None, output_tokens=None, cost_estimate=None, fallback_used=False, fallback_chain=[], error=None)
            except Exception as exc:
                return ModelResponse(ok=False, content=None, model_id=profile.id, provider=self.provider, endpoint=profile.endpoint, latency_ms=0.0, input_tokens=None, output_tokens=None, cost_estimate=None, fallback_used=False, fallback_chain=[], error=f"image_request_error:{exc}")
        payload = {
            "model": profile.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": profile.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": schema, "strict": True},
            },
        }
        # Modelos de raciocínio (qwen3.5:397b, gpt-oss-120b) em ollama-cloud/nvidia:
        # o endpoint IGNORA json_schema strict e devolve markdown, e o CoT polui o
        # content. Usa json_object (schema no prompt) + reasoning_effort none p/
        # devolver JSON limpo e determinístico.
        if (profile.legacy_provider or "") in ("ollama-cloud", "nvidia"):
            payload["response_format"] = {"type": "json_object"}
            payload["messages"] = [
                {**m, "content": f"{m.get('content', '')}\n\nOUTPUT MUST MATCH THIS JSON SCHEMA EXACTLY:\n{json.dumps(schema)}"}
                if m.get("role") == "system" else m
                for m in messages
            ]
            payload["reasoning_effort"] = "none"
        data, err = self._post(profile, "/chat/completions", payload, timeout_s or 60)
        if err:
            return ModelResponse(ok=False, content=None, model_id=profile.id, provider=self.provider,
                                  endpoint=profile.endpoint, latency_ms=0.0, input_tokens=None,
                                  output_tokens=None, cost_estimate=None, fallback_used=False,
                                  fallback_chain=[], error=err)
        choices = data.get("choices")
        if not choices:
            return ModelResponse(ok=False, content=None, model_id=profile.id, provider=self.provider,
                                  endpoint=profile.endpoint, latency_ms=0.0, input_tokens=None,
                                  output_tokens=None, cost_estimate=None, fallback_used=False,
                                  fallback_chain=[], error="malformed_response:no_choices", raw=data)
        raw_content = choices[0].get("message", {}).get("content")
        try:
            parsed = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
        except (ValueError, TypeError, json.JSONDecodeError):
            return ModelResponse(ok=False, content=raw_content, model_id=profile.id, provider=self.provider,
                                  endpoint=profile.endpoint, latency_ms=0.0, input_tokens=None,
                                  output_tokens=None, cost_estimate=None, fallback_used=False,
                                  fallback_chain=[], error="structured_output_not_json", raw=data)
        usage = data.get("usage") or {}
        return ModelResponse(
            ok=True, content=parsed, model_id=profile.id, provider=self.provider,
            endpoint=profile.endpoint, latency_ms=0.0,
            input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
            cost_estimate=self._estimate_cost(profile, usage.get("prompt_tokens"), usage.get("completion_tokens")),
            fallback_used=False, fallback_chain=[], error=None, raw=data,
        )

    def embed(self, profile, texts, timeout_s=60, **_):
        from core.model_gateway import EmbeddingResponse
        if not profile.capabilities.embeddings:
            return self._unsupported_embedding(profile, "embeddings")
        payload = {"model": profile.model, "input": texts}
        data, err = self._post(profile, "/embeddings", payload, timeout_s or 60)
        if err:
            return EmbeddingResponse(ok=False, vectors=[], model_id=profile.id, provider=self.provider,
                                      endpoint=profile.endpoint, latency_ms=0.0, error=err)
        items = data.get("data") or []
        vectors = [item.get("embedding", []) for item in items]
        return EmbeddingResponse(ok=True, vectors=vectors, model_id=profile.id, provider=self.provider,
                                  endpoint=profile.endpoint, latency_ms=0.0, raw=data)

    def rerank(self, profile, query, documents, timeout_s=60, **_):
        from core.model_gateway import RerankResponse
        if not profile.capabilities.rerank:
            return self._unsupported_rerank(profile, "rerank")
        payload = {"model": profile.model, "query": query, "documents": documents}
        data, err = self._post(profile, "/rerank", payload, timeout_s or 60)
        if err:
            return RerankResponse(ok=False, results=[], model_id=profile.id, provider=self.provider,
                                   endpoint=profile.endpoint, latency_ms=0.0, error=err)
        results = data.get("results") or []
        if len(results) != len(documents):
            return RerankResponse(
                ok=False, results=[], model_id=profile.id, provider=self.provider,
                endpoint=profile.endpoint, latency_ms=0.0,
                error=f"result_count_mismatch:{len(results)}!={len(documents)}", raw=data,
            )
        return RerankResponse(ok=True, results=results, model_id=profile.id, provider=self.provider,
                               endpoint=profile.endpoint, latency_ms=0.0, raw=data)

    def health(self, profile) -> dict:
        try:
            resp = requests.get(f"{self._base_url(profile)}/models", headers=self._headers(profile), timeout=5)
            healthy = resp.status_code == 200
        except requests.exceptions.RequestException:
            healthy = False
        except ValueError:
            healthy = False
        return {"model_id": profile.id, "provider": self.provider, "endpoint": profile.endpoint,
                "healthy": healthy}

    def _estimate_cost(self, profile, input_tokens, output_tokens) -> Optional[float]:
        if profile.input_cost_per_1k is None or profile.output_cost_per_1k is None:
            return None
        if input_tokens is None or output_tokens is None:
            return None
        return (input_tokens / 1000.0) * profile.input_cost_per_1k + \
            (output_tokens / 1000.0) * profile.output_cost_per_1k
