"""EC-3 — Profile com `unsupported_reason` é listado mas NÃO executa adapter.

Regras esperadas:
  * aparece em `validate()` como `unsupported_explicit`
  * aparece em relatório como unsupported_explicit
  * não é selecionado para execução normal
  * não tenta adapter em runtime
  * gera erro claro se for o único disponível em MODEL_GATEWAY_MODE=on
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import BaseModel

from core import llm_client
from core.model_gateway import ModelGateway, ModelResponse
from core.model_registry import (
    ModelCapabilities,
    ModelProfile,
    ModelRegistry,
)


def _unsupported_profile(pid: str = "future-llm", level: str = "primary") -> ModelProfile:
    return ModelProfile(
        id=pid,
        provider="native",  # placeholder
        model="future-1",
        endpoint=None,
        roles=["dreamer", *(["fallback"] if level != "primary" else [])],
        role="dreamer",
        level=level,
        capabilities=ModelCapabilities(chat=True, structured_output=True),
        unsupported_reason="not_in_PROVIDERS_CONFIG",
        legacy_provider=pid,
    )


def _capable_profile(pid: str = "ollama-fb", level: str = "fallback") -> ModelProfile:
    return ModelProfile(
        id=pid,
        provider="openai_compatible",
        model="llama3.1",
        endpoint="http://localhost:11434/v1",
        api_key_env="OLLAMA_LOCAL",
        roles=["dreamer", "fallback"],
        role="dreamer",
        level=level,
        capabilities=ModelCapabilities(chat=True, structured_output=True),
        legacy_provider="ollama",
    )


def test_unsupported_listed_in_validate():
    reg = ModelRegistry([_unsupported_profile()])
    problems = reg.validate()
    issues = [p.get("issue") for p in problems]
    assert "unsupported_explicit" in issues


def test_unsupported_not_executed_at_runtime(capsys):
    """An unsupported profile MUST NOT trigger an adapter call. The
    gateway skips it (emits a `provider_unsupported_skipped` event) and
    moves on to the next candidate."""
    reg = ModelRegistry([
        _unsupported_profile(pid="future-llm", level="primary"),
        _capable_profile(pid="ollama-fb", level="fallback"),
    ])
    gateway = ModelGateway(reg)

    class _ShouldNotRun:
        def chat(self, *args, **kwargs):
            raise AssertionError("unsupported profile MUST NOT be dispatched")
        def structured(self, *args, **kwargs):
            raise AssertionError("unsupported profile MUST NOT be dispatched (structured)")

    class _CapableAdapter:
        def chat(self, profile, *args, **kwargs):
            return ModelResponse(
                ok=True, content={"ok": True}, model_id=profile.id,
                provider=profile.provider, endpoint=profile.endpoint,
                latency_ms=1.0, input_tokens=1, output_tokens=1,
                cost_estimate=None, fallback_used=True, fallback_chain=["future-llm", profile.id],
                error=None,
            )

    def adapter_factory(provider):
        return _CapableAdapter() if provider == "openai_compatible" else _ShouldNotRun()

    with patch("core.model_gateway._adapter_for", side_effect=adapter_factory):
        resp = gateway.chat(
            messages=[{"role": "user", "content": "hi"}], role="dreamer",
        )
    assert resp.ok is True
    assert resp.model_id.endswith("ollama-fb")

    out = capsys.readouterr().err
    assert "provider_unsupported_skipped" in out
    # And the unsupported profile's model/id is recorded, not leaked secrets.
    assert "future-llm" in out


def test_only_unsupported_available_returns_structured_error():
    """If the chain is entirely unsupported, the gateway returns a
    structured error (`no_qualifying_provider`) without crashing."""
    reg = ModelRegistry([
        _unsupported_profile(pid="future-llm", level="primary"),
    ])
    gateway = ModelGateway(reg)

    class _ShouldNotRun:
        def chat(self, *args, **kwargs):
            raise AssertionError("must not be called")
        def structured(self, *args, **kwargs):
            raise AssertionError("must not be called")

    with patch("core.model_gateway._adapter_for", return_value=_ShouldNotRun()):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="dreamer")
    assert resp.ok is False
    assert resp.error == "no_qualifying_provider"


def test_unsupported_only_in_mode_on_raises_structured(monkeypatch, capsys):
    """In MODEL_GATEWAY_MODE=on, an unsupported-only chain MUST propagate
    as a structured error — never silently fall through to legacy."""
    monkeypatch.setenv("MODEL_GATEWAY_MODE", "on")
    monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "future-llm")
    monkeypatch.setenv("HIVE_DREAMER_MODEL", "future-1")

    class _Answer(BaseModel):
        ok: bool

    def fail_legacy(*args, **kwargs):
        raise AssertionError("legacy MUST NOT be called in MODE=on")

    with patch.object(llm_client, "_legacy_call_llm_with_fallback", side_effect=fail_legacy), \
         patch.object(llm_client, "_call_via_model_gateway", return_value=None):
        with pytest.raises(RuntimeError, match="MODE=on"):
            llm_client.call_llm_with_fallback("dreamer", "hi", "sys", _Answer)


def test_unsupported_skipped_event_redacts_secrets(capsys):
    """EC-3 / R10.3 — the skip event MUST NOT carry secrets. A profile
    with a secret-laden `unsupported_reason` is still safe."""
    profile = ModelProfile(
        id="leaky",
        provider="native",
        model="x",
        endpoint="http://example.com",
        roles=["dreamer"],
        role="dreamer",
        level="primary",
        capabilities=ModelCapabilities(chat=True, structured_output=True),
        unsupported_reason=f"error with secret sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcde",
        legacy_provider="leaky",
    )
    reg = ModelRegistry([profile])
    gateway = ModelGateway(reg)
    with patch("core.model_gateway._adapter_for") as adapter_ctor:
        adapter_ctor.side_effect = AssertionError("should not be called")
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="dreamer")
    assert resp.ok is False
    out = capsys.readouterr().err
    assert "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcde" not in out
    assert "REDACTED:token" in out
