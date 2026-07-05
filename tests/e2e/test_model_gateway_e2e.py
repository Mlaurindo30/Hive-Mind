"""
tests/e2e/test_model_gateway_e2e.py — Model Gateway (Priority 1) end-to-end.

Spec: specs/model-gateway.md § 10.4.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.model_gateway import ModelGateway, ModelResponse
from core.model_registry import ModelCapabilities, ModelProfile, ModelRegistry

FAKE_SECRET = "sk-proj-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"


class _Answer(BaseModel):
    response: str


def test_gateway_disabled_legacy_llm_client_still_works(monkeypatch):
    """In the post-unification build, the gateway is the default path
    (R4 §1). `MODEL_GATEWAY_MODE=off` and `HIVE_FORCE_LEGACY_LLM=true`
    are the only ways to keep the legacy path. This test pins that:
    when the gateway is forced off via `HIVE_FORCE_LEGACY_LLM=true`,
    the legacy path runs and a missing role config still raises the
    canonical `RuntimeError` from the legacy code."""
    monkeypatch.setenv("HIVE_FORCE_LEGACY_LLM", "true")
    monkeypatch.delenv("MODEL_GATEWAY_ENABLED", raising=False)
    from core.llm_client import call_llm_with_fallback

    with patch("core.llm_client.get_role_config", return_value=None):
        with pytest.raises(RuntimeError, match="Nenhum LLM configurado"):
            call_llm_with_fallback("nonexistent-role", "p", "s", _Answer)


def test_gateway_enabled_selects_model_by_role():
    registry = ModelRegistry([
        ModelProfile(id="wrong-role", provider="native", model="x", roles=["dreamer"], priority=1),
        ModelProfile(id="right-role", provider="native", model="y", roles=["validator"], priority=1),
    ])
    gateway = ModelGateway(registry)

    class FakeAdapter:
        def chat(self, profile, messages, **kwargs):
            return ModelResponse(ok=True, content="hi", model_id=profile.id, provider=profile.provider,
                                  endpoint=None, latency_ms=1.0, input_tokens=1, output_tokens=1,
                                  cost_estimate=None, fallback_used=False, fallback_chain=[], error=None)

    with patch("core.model_gateway._adapter_for", return_value=FakeAdapter()):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")
    assert resp.model_id == "right-role"


def test_structured_validator_returns_schema_valid_json():
    registry = ModelRegistry([
        ModelProfile(id="v", provider="native", model="x", roles=["validator"],
                     capabilities=ModelCapabilities(structured_output=True)),
    ])
    gateway = ModelGateway(registry)

    class FakeAdapter:
        def structured(self, profile, messages, schema, **kwargs):
            return ModelResponse(ok=True, content={"valid": True}, model_id=profile.id,
                                  provider=profile.provider, endpoint=None, latency_ms=1.0,
                                  input_tokens=1, output_tokens=1, cost_estimate=None,
                                  fallback_used=False, fallback_chain=[], error=None)

    schema = {"type": "object", "properties": {"valid": {"type": "boolean"}}, "required": ["valid"]}
    with patch("core.model_gateway._adapter_for", return_value=FakeAdapter()):
        resp = gateway.structured(messages=[{"role": "user", "content": "hi"}], schema=schema, role="validator")
    assert resp.ok is True
    assert resp.content == {"valid": True}


def test_local_fallback_failure_uses_configured_fallback():
    registry = ModelRegistry([
        ModelProfile(id="local", provider="native", model="x", roles=["validator"], priority=1,
                     fallback_chain=["cloud"]),
        ModelProfile(id="cloud", provider="native", model="y", roles=["fallback"], priority=50),
    ])
    gateway = ModelGateway(registry)

    class FakeAdapter:
        def chat(self, profile, messages, **kwargs):
            if profile.id == "local":
                return ModelResponse(ok=False, content=None, model_id=profile.id, provider=profile.provider,
                                      endpoint=None, latency_ms=1.0, input_tokens=None, output_tokens=None,
                                      cost_estimate=None, fallback_used=False, fallback_chain=[],
                                      error="connection_refused")
            return ModelResponse(ok=True, content="from cloud", model_id=profile.id, provider=profile.provider,
                                  endpoint=None, latency_ms=1.0, input_tokens=1, output_tokens=1,
                                  cost_estimate=None, fallback_used=False, fallback_chain=[], error=None)

    with patch("core.model_gateway._adapter_for", return_value=FakeAdapter()):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")
    assert resp.ok is True
    assert resp.model_id == "cloud"
    assert resp.fallback_used is True


def test_fallback_exhausted_returns_structured_error_not_exception():
    registry = ModelRegistry([
        ModelProfile(id="local", provider="native", model="x", roles=["validator"], priority=1,
                     fallback_chain=["cloud"]),
        ModelProfile(id="cloud", provider="native", model="y", roles=["fallback"], priority=50),
    ])
    gateway = ModelGateway(registry)

    class AllFailAdapter:
        def chat(self, profile, messages, **kwargs):
            return ModelResponse(ok=False, content=None, model_id=profile.id, provider=profile.provider,
                                  endpoint=None, latency_ms=1.0, input_tokens=None, output_tokens=None,
                                  cost_estimate=None, fallback_used=False, fallback_chain=[],
                                  error="connection_refused")

    with patch("core.model_gateway._adapter_for", return_value=AllFailAdapter()):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")
    assert resp.ok is False
    assert isinstance(resp.error, str) and resp.error
    assert resp.fallback_used is True
    assert resp.fallback_chain == ["local", "cloud"]


def test_health_includes_model_gateway_key():
    from core.memory.health import health_check
    status = health_check("nmem", "/tmp/does-not-exist.json", "http://localhost:1", "/tmp", 3)
    assert "model_gateway" in status
    assert "enabled" in status["model_gateway"]


def test_telemetry_omits_raw_prompt_and_redacts_secret(capsys):
    registry = ModelRegistry([ModelProfile(id="a", provider="native", model="x", roles=["validator"])])
    gateway = ModelGateway(registry)

    class LeakyAdapter:
        def chat(self, profile, messages, **kwargs):
            return ModelResponse(ok=False, content=None, model_id=profile.id, provider=profile.provider,
                                  endpoint=None, latency_ms=1.0, input_tokens=None, output_tokens=None,
                                  cost_estimate=None, fallback_used=False, fallback_chain=[],
                                  error=f"auth_error api_key={FAKE_SECRET}")

    prompt_with_secret = f"my prompt contains {FAKE_SECRET} inline"
    with patch("core.model_gateway._adapter_for", return_value=LeakyAdapter()):
        gateway.chat(messages=[{"role": "user", "content": prompt_with_secret}], role="validator")

    captured = capsys.readouterr()
    assert "[model_gateway]" in captured.err
    assert prompt_with_secret not in captured.err  # telemetry never carries the raw prompt
    assert FAKE_SECRET not in captured.err          # and the error itself is redacted


def test_redactor_removes_secret_from_final_error():
    registry = ModelRegistry([ModelProfile(id="a", provider="native", model="x", roles=["validator"])])
    gateway = ModelGateway(registry)

    class LeakyAdapter:
        def chat(self, profile, messages, **kwargs):
            raise RuntimeError(f"leaked {FAKE_SECRET}")

    with patch("core.model_gateway._adapter_for", return_value=LeakyAdapter()):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")
    assert FAKE_SECRET not in resp.error
