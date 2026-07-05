from __future__ import annotations

import pytest

pytestmark = pytest.mark.real

"""Model Gateway — real openai_compatible backend (Ollama's built-in /v1 API).

Spec: specs/model-gateway.md D15.

No dedicated LM Studio/llama.cpp/vLLM/SGLang/LiteLLM server was running in
this environment when this build was authored (LM Studio's `lms` CLI is
installed but has zero models downloaded; no other server was up). Ollama
was already running locally and exposes the same OpenAI-compatible /v1
surface that `integrations/model_gateway/openai_compatible_adapter.py`
targets — the exact adapter class also used, unmodified, by the lmstudio/
llamacpp/vllm/sglang provider labels. This test exercises that shared
adapter code for real against a real, already-running local backend,
satisfying D15's "at least one real OpenAI-compatible backend" without a
false pass.
"""
import socket

from core.model_gateway import ModelGateway

OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434


def _ollama_reachable() -> bool:
    try:
        with socket.create_connection((OLLAMA_HOST, OLLAMA_PORT), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def gateway():
    if not _ollama_reachable():
        pytest.skip(f"Ollama not reachable at {OLLAMA_HOST}:{OLLAMA_PORT} — no real backend configured")
    return ModelGateway.from_config()


def test_health_reports_the_backend_reachable(gateway):
    health = gateway.health()
    detail = next((d for d in health["details"] if d["model_id"] == "ollama-openai-compat"), None)
    assert detail is not None, "ollama-openai-compat profile missing from config/model-gateway.yaml"
    assert detail["healthy"] is True


def test_real_chat_call(gateway):
    resp = gateway.chat(
        messages=[{"role": "user", "content": "Reply with exactly one word: PONG"}],
        model_id="ollama-openai-compat",
    )
    assert resp.ok is True, resp.error
    assert resp.provider == "openai_compatible"
    assert isinstance(resp.content, str) and resp.content.strip()
    assert resp.latency_ms > 0
    assert resp.error is None


def test_real_structured_call_validates_schema(gateway):
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    resp = gateway.structured(
        messages=[{"role": "user", "content": 'Return this exact JSON: {"answer": "42"}'}],
        schema=schema,
        model_id="ollama-openai-compat",
    )
    assert resp.ok is True, resp.error
    assert isinstance(resp.content, dict)
    assert "answer" in resp.content


def test_real_call_does_not_give_false_ok_when_service_is_actually_offline():
    """Sanity check for the anti-false-pass rule: an unreachable endpoint
    must return ok=False, never a fabricated success."""
    from core.model_registry import ModelCapabilities, ModelProfile, ModelRegistry

    registry = ModelRegistry([
        ModelProfile(id="dead", provider="openai_compatible", model="x",
                     endpoint="http://127.0.0.1:1/v1", roles=["validator"],
                     capabilities=ModelCapabilities(chat=True)),
    ])
    gateway = ModelGateway(registry)
    resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], model_id="dead")
    assert resp.ok is False
    assert resp.error == "connection_refused"
