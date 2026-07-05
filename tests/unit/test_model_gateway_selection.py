"""
tests/unit/test_model_gateway_selection.py — ModelGateway role/capability
selection and fallback, with a fake adapter (no real network).

Spec: specs/model-gateway.md Requirements 10-13, Edge Cases 18-19.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.model_gateway import ModelGateway, ModelResponse
from core.model_registry import ModelCapabilities, ModelProfile, ModelRegistry


class FakeAdapter:
    """Deterministic stand-in for a real HTTP adapter, keyed by model id."""

    def __init__(self, behavior: dict[str, str]):
        self.behavior = behavior  # model_id -> "ok" | "fail"
        self.calls: list[str] = []

    def chat(self, profile, messages, **kwargs):
        self.calls.append(profile.id)
        if self.behavior.get(profile.id) == "ok":
            return ModelResponse(ok=True, content="hello", model_id=profile.id,
                                  provider=profile.provider, endpoint=profile.endpoint,
                                  latency_ms=1.0, input_tokens=5, output_tokens=2,
                                  cost_estimate=None, fallback_used=False, fallback_chain=[],
                                  error=None)
        return ModelResponse(ok=False, content=None, model_id=profile.id,
                              provider=profile.provider, endpoint=profile.endpoint,
                              latency_ms=1.0, input_tokens=None, output_tokens=None,
                              cost_estimate=None, fallback_used=False, fallback_chain=[],
                              error="connection_refused")

    structured = chat  # same behavior for these tests
    embed = None
    rerank = None
    health = None


def _registry_with_chain():
    return ModelRegistry([
        ModelProfile(id="primary", provider="openai_compatible", model="x",
                     endpoint="http://x/v1", roles=["validator"], priority=1,
                     capabilities=ModelCapabilities(structured_output=True),
                     fallback_chain=["secondary"]),
        ModelProfile(id="secondary", provider="openai_compatible", model="y",
                     endpoint="http://y/v1", roles=["fallback"], priority=50,
                     capabilities=ModelCapabilities(structured_output=True)),
    ])


def test_select_by_role_and_capability_together():
    registry = ModelRegistry([
        ModelProfile(id="plain", provider="native", model="x", roles=["validator"], priority=1),
        ModelProfile(id="structured", provider="native", model="y", roles=["validator"],
                     priority=99, capabilities=ModelCapabilities(structured_output=True)),
    ])
    gateway = ModelGateway(registry)
    with patch("core.model_gateway._adapter_for", return_value=FakeAdapter({"plain": "ok", "structured": "ok"})):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")
        assert resp.model_id == "plain"  # lower priority wins when require= isn't set
        resp2 = gateway.structured(messages=[{"role": "user", "content": "hi"}],
                                    schema={"type": "object"}, role="validator")
        assert resp2.model_id == "structured"  # structured() requires structured_output


def test_fallback_chain_is_walked_on_failure():
    registry = _registry_with_chain()
    gateway = ModelGateway(registry)
    fake = FakeAdapter({"primary": "fail", "secondary": "ok"})
    with patch("core.model_gateway._adapter_for", return_value=fake):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")
    assert resp.ok is True
    assert resp.model_id == "secondary"
    assert resp.fallback_used is True
    assert resp.fallback_chain == ["primary", "secondary"]
    assert fake.calls == ["primary", "secondary"]


def test_all_fallbacks_exhausted_returns_ok_false_not_raise():
    registry = _registry_with_chain()
    gateway = ModelGateway(registry)
    fake = FakeAdapter({"primary": "fail", "secondary": "fail"})
    with patch("core.model_gateway._adapter_for", return_value=fake):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")
    assert resp.ok is False
    assert resp.error is not None
    assert resp.fallback_used is True
    assert resp.fallback_chain == ["primary", "secondary"]


def test_fallback_to_disabled_model_is_skipped():
    registry = ModelRegistry([
        ModelProfile(id="primary", provider="native", model="x", roles=["validator"],
                     priority=1, fallback_chain=["disabled-fb", "real-fb"]),
        ModelProfile(id="disabled-fb", provider="native", model="y", enabled=False,
                     roles=["fallback"], priority=10),
        ModelProfile(id="real-fb", provider="native", model="z", roles=["fallback"], priority=20),
    ])
    gateway = ModelGateway(registry)
    fake = FakeAdapter({"primary": "fail", "real-fb": "ok"})
    with patch("core.model_gateway._adapter_for", return_value=fake):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")
    assert resp.ok is True
    assert resp.model_id == "real-fb"
    assert "disabled-fb" not in fake.calls


def test_fallback_cycle_does_not_loop_forever():
    registry = ModelRegistry([
        ModelProfile(id="a", provider="native", model="x", roles=["validator"], priority=1,
                     fallback_chain=["b"]),
        ModelProfile(id="b", provider="native", model="y", roles=["fallback"], priority=10,
                     fallback_chain=["a"]),  # cycle back to a
    ])
    gateway = ModelGateway(registry)
    fake = FakeAdapter({"a": "fail", "b": "fail"})
    with patch("core.model_gateway._adapter_for", return_value=fake):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")
    assert resp.ok is False
    # 'a' attempted once (primary) + 'b' attempted once (fallback); the cycle back to 'a' is not retried
    assert fake.calls.count("a") == 1


def test_structured_rejects_schema_violating_response():
    registry = ModelRegistry([
        ModelProfile(id="a", provider="openai_compatible", model="x", endpoint="http://x/v1",
                     roles=["validator"], priority=1,
                     capabilities=ModelCapabilities(structured_output=True)),
    ])
    gateway = ModelGateway(registry)

    class BadJsonAdapter:
        def structured(self, profile, messages, schema, **kwargs):
            # returns valid JSON, but missing the required 'answer' field
            return ModelResponse(ok=True, content={"wrong_field": 1}, model_id=profile.id,
                                  provider=profile.provider, endpoint=profile.endpoint,
                                  latency_ms=1.0, input_tokens=1, output_tokens=1,
                                  cost_estimate=None, fallback_used=False, fallback_chain=[],
                                  error=None)

    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    with patch("core.model_gateway._adapter_for", return_value=BadJsonAdapter()):
        resp = gateway.structured(messages=[{"role": "user", "content": "hi"}], schema=schema, role="validator")
    assert resp.ok is False
    assert "schema_invalid" in resp.error
