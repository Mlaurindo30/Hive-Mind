"""D4 — Real OpenAI-compat backend smoke (ollama / lmstudio).

This is the only test in the suite that touches a live HTTP endpoint.
If neither ollama (`http://127.0.0.1:11434/v1`) nor lmstudio
(`http://127.0.0.1:1234/v1`) is listening, the test is skipped with
the reason recorded in the pytest output.
"""
from __future__ import annotations

import time
import uuid

import pytest
import requests

from core.model_gateway import ModelGateway, ModelResponse
from core.model_registry import ModelRegistry


def _is_openai_compat_alive(base_url: str) -> bool:
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/models", timeout=2)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


@pytest.fixture
def openai_compat_backend():
    """Return (base_url, model_id) for a live local OpenAI-compat
    backend, or skip the test if none is available."""
    candidates = [
        ("http://127.0.0.1:11434/v1", "qwen2.5:3b"),
        ("http://127.0.0.1:1234/v1", "local-model"),
    ]
    for base_url, default_model in candidates:
        if _is_openai_compat_alive(base_url):
            # Try to read the actual model list — ollama serves it; lmstudio
            # too with a slightly different shape. Either way, fall back
            # to the default model.
            try:
                resp = requests.get(f"{base_url.rstrip('/')}/models", timeout=2)
                data = resp.json()
                items = data.get("data") or data.get("models") or []
                model_id = items[0]["id"] if items else default_model
            except Exception:
                model_id = default_model
            return base_url, model_id
    pytest.skip(
        "no live OpenAI-compat backend (ollama:11434 or lmstudio:1234) — "
        "D4 backend-real test skipped"
    )


def test_openai_compat_real_chat(monkeypatch, openai_compat_backend):
    """Exercise ModelGateway with a real local backend in MODE=on
    (R3 §3, D4). Asserts:
      * `ModelResponse.ok is True`
      * `fallback_used is False`
      * `provider` and `model` match the role configured.
    """
    base_url, model_id = openai_compat_backend
    monkeypatch.setenv("MODEL_GATEWAY_MODE", "on")
    # Use the legacy `openai` provider name (it maps to the
    # `openai_compatible` adapter) so `PROVIDERS_CONFIG` provides
    # `endpoint` and `api_key_env`. We then overwrite `endpoint` to
    # point at the local ollama/lmstudio URL.
    monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "openai")
    monkeypatch.setenv("HIVE_DREAMER_MODEL", model_id)

    # Build a registry that pins the role to the live backend.
    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    primary = next(p for p in reg.list_models() if p.level == "primary")
    primary.endpoint = base_url
    primary.api_key_env = None  # local — no auth
    primary.capabilities = primary.capabilities.__class__(
        chat=True, structured_output=True, json_schema=True,
    )

    gateway = ModelGateway(reg)
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    response = gateway.chat(
        messages=[
            {"role": "user", "content": "Responda exatamente: OK"},
        ],
        role="dreamer",
        timeout_s=30,
    )
    elapsed = (time.monotonic() - started) * 1000
    print(
        f"\n[d4] real backend {base_url} responded in {elapsed:.0f}ms "
        f"(ok={response.ok}, error={response.error!r})"
    )

    assert isinstance(response, ModelResponse)
    assert response.ok is True, f"backend returned ok=False: {response.error}"
    assert response.fallback_used is False
    assert model_id in response.model_id
