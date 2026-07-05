"""R8.3 — Erro canônico `no_vision_capable_provider`.

Quando o chamador exige `vision=True` e nenhum profile da role é
vision-capable, o gateway DEVE retornar
`ModelResponse(ok=False, error='no_vision_capable_provider')` antes de
qualquer dispatch. Este módulo cobre:

  * require={"vision": True} com todos os providers sem vision
  * error == "no_vision_capable_provider"
  * adapter NÃO é chamado
  * em MODEL_GATEWAY_MODE=on, o wrapper NÃO cai pro legado
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import BaseModel

from core.model_gateway import ModelGateway, ModelResponse
from core.model_registry import (
    ModelCapabilities,
    ModelProfile,
    ModelRegistry,
)


def _profile(
    *, pid: str, role: str = "vision", level: str = "primary",
    vision: bool = False,
) -> ModelProfile:
    return ModelProfile(
        id=pid,
        provider="native",
        model=f"model-{pid}",
        endpoint="http://localhost:0",
        roles=[role, *(["fallback"] if level != "primary" else [])],
        role=role,
        level=level,
        capabilities=ModelCapabilities(chat=True, structured_output=True, vision=vision),
    )


def test_no_vision_provider_returns_canonical_error():
    """The chain has zero vision-capable profiles; the gateway returns
    the canonical error string before any adapter call."""
    reg = ModelRegistry([
        _profile(pid="v1", level="primary", vision=False),
        _profile(pid="v2", level="fallback", vision=False),
        _profile(pid="v3", level="fallback2", vision=False),
    ])
    gateway = ModelGateway(reg)

    class _ShouldNotRun:
        def chat(self, *args, **kwargs):
            raise AssertionError("adapter MUST NOT be called when no vision provider exists")
        def structured(self, *args, **kwargs):
            raise AssertionError("adapter MUST NOT be called for structured either")

    with patch("core.model_gateway._adapter_for", return_value=_ShouldNotRun()):
        resp = gateway.chat(
            messages=[{"role": "user", "content": "describe this image"}],
            role="vision",
            require={"vision": True},
        )
    assert isinstance(resp, ModelResponse)
    assert resp.ok is False
    assert resp.error == "no_vision_capable_provider"


def test_no_vision_provider_structured_also_canonical():
    """Same canonical error path for `structured()` — the pre-flight
    check is the same regardless of capability method."""
    reg = ModelRegistry([
        _profile(pid="v1", level="primary", vision=False),
    ])
    gateway = ModelGateway(reg)
    with patch("core.model_gateway._adapter_for") as adapter_ctor:
        adapter_ctor.side_effect = AssertionError("should not be called")
        resp = gateway.structured(
            messages=[{"role": "user", "content": "describe"}],
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            role="vision",
            require={"vision": True},
        )
    assert resp.ok is False
    assert resp.error == "no_vision_capable_provider"


def test_vision_provider_succeeds():
    """Sanity: when at least one profile has vision=True, the call
    dispatches and the canonical error does NOT fire."""
    reg = ModelRegistry([
        _profile(pid="plain", level="primary", vision=False),
        _profile(pid="sees", level="fallback", vision=True),
    ])
    gateway = ModelGateway(reg)

    class _VisionAdapter:
        def chat(self, profile, *args, **kwargs):
            return ModelResponse(
                ok=True, content={"answer": "red square"},
                model_id=profile.id, provider=profile.provider,
                endpoint=profile.endpoint, latency_ms=1.0,
                input_tokens=1, output_tokens=1, cost_estimate=None,
                fallback_used=True, fallback_chain=["plain", "sees"],
                error=None,
            )

    with patch("core.model_gateway._adapter_for", return_value=_VisionAdapter()):
        resp = gateway.chat(
            messages=[{"role": "user", "content": "describe this image"}],
            role="vision",
            require={"vision": True},
        )
    assert resp.ok is True
    # The vision-capable profile is the only one that satisfies `vision`
    # so it must be the one dispatched.
    assert "sees" in resp.model_id


def test_no_vision_provider_does_not_fall_back_to_legacy_in_mode_on(monkeypatch):
    """In MODEL_GATEWAY_MODE=on, the canonical vision error MUST
    propagate — the wrapper MUST NOT silently fall through to the
    legacy `_legacy_call_llm_with_fallback`."""
    from core import llm_client
    monkeypatch.setenv("MODEL_GATEWAY_MODE", "on")
    monkeypatch.setenv("HIVE_VISION_PROVIDER", "ollama")
    monkeypatch.setenv("HIVE_VISION_MODEL", "llava")

    class _Answer(BaseModel):
        ok: bool

    def fail_legacy(*args, **kwargs):
        raise AssertionError("legacy MUST NOT be called when vision is required")

    with patch.object(llm_client, "_legacy_call_llm_with_fallback", side_effect=fail_legacy), \
         patch.object(llm_client, "_call_via_model_gateway") as gw:
        # The wrapper calls _call_via_model_gateway, which itself goes
        # through ModelGateway and returns the ModelResponse(ok=False,
        # error="no_vision_capable_provider"). In MODE=on, that propagates.
        gw.return_value = None  # legacy expects a non-None to short-circuit
        with pytest.raises(RuntimeError, match="MODE=on"):
            llm_client.call_llm_with_fallback("vision", "describe this image", "", _Answer)


def test_vision_preflight_does_not_break_when_role_has_no_profiles():
    """If the role is unknown, the pre-flight returns an empty list and
    the canonical error still fires (the operator gets a clear signal
    that no vision-capable provider exists for that role)."""
    reg = ModelRegistry([
        _profile(pid="v1", level="primary", vision=True, role="vision"),
    ])
    gateway = ModelGateway(reg)
    with patch("core.model_gateway._adapter_for") as adapter_ctor:
        adapter_ctor.side_effect = AssertionError("should not be called")
        resp = gateway.chat(
            messages=[{"role": "user", "content": "describe this image"}],
            role="no-such-role",
            require={"vision": True},
        )
    assert resp.ok is False
    assert resp.error == "no_vision_capable_provider"
