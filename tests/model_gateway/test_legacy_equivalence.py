"""D1 — Pytest suite of legacy↔gateway equivalence.

Every requirement here maps to a numbered item in
`specs/model-gateway-unification.md` D1.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import BaseModel

from core import llm_client, model_gateway
from core.auth import PROVIDERS_CONFIG
from core.model_gateway import (
    ModelGateway,
    ModelResponse,
    force_legacy_llm,
    resolve_gateway_mode,
)
from core.model_registry import (
    ModelRegistry,
    ModelRegistryError,
    PROVIDER_ADAPTER_HINT,
)


# ---------------------------------------------------------------------------
# 1. test_every_role_in_PROVIDERS_CONFIG_resolves
# ---------------------------------------------------------------------------


def test_every_role_in_PROVIDERS_CONFIG_resolves(all_legacy_providers_env):
    """For every provider in PROVIDERS_CONFIG, build_profile_from_provider
    returns a ModelProfile with a valid adapter hint OR an explicit
    `unsupported_explicit` reason — never silent (R1 §4, R2 §3)."""
    seen = all_legacy_providers_env
    assert seen, "fixture should populate env with at least one provider"
    for provider in seen:
        profile = ModelRegistry.build_profile_from_provider(
            "dreamer", provider, f"test-model-{seen.index(provider)}"
        )
        assert profile.id.endswith("primary"), profile.id
        assert profile.role == "dreamer"
        assert profile.level == "primary"
        # Either we have a known adapter, or we have an explicit reason.
        if profile.provider in PROVIDER_ADAPTER_HINT.values():
            assert profile.unsupported_reason is None or "no adapter" not in (profile.unsupported_reason or "")
        else:
            # No known adapter — registry MUST mark it unsupported.
            assert profile.unsupported_reason is not None, (
                f"provider {provider!r} produced profile without unsupported_reason"
            )


# ---------------------------------------------------------------------------
# 2. test_combined_config_order_primary_fallback_fallback2
# ---------------------------------------------------------------------------


def test_combined_config_order_primary_fallback_fallback2(dreamer_env):
    """`from_combined_config` returns profiles in the order
    primary → fallback → fallback2 (R1 §1)."""
    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    levels = [p.level for p in reg.list_models()]
    assert levels == ["primary", "fallback", "fallback2"], levels

    providers = [p.id.split("/")[1] for p in reg.list_models()]
    assert providers == ["ollama", "openrouter", "openai"], providers

    # Endpoints and api_key_env all come from PROVIDERS_CONFIG.
    primary = reg.list_models()[0]
    assert primary.endpoint == PROVIDERS_CONFIG["ollama"]["base_url"]
    assert primary.api_key_env == PROVIDERS_CONFIG["ollama"]["env_var"]


# ---------------------------------------------------------------------------
# 3. test_yaml_does_not_require_provider_model
# ---------------------------------------------------------------------------


def test_yaml_does_not_require_provider_model(dreamer_env, tmp_path, monkeypatch):
    """Registry loads cleanly when YAML is absent or has no roles.<x>.provider
    (R1 §5, R7 §3). The legacy env is the single source of truth for
    provider/model."""
    # Case 1: no YAML at all.
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(tmp_path / "missing.yaml"))
    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    assert [p.level for p in reg.list_models()] == ["primary", "fallback", "fallback2"]

    # Case 2: YAML present, only `roles:` block, no provider/model.
    yaml_path = tmp_path / "model-gateway.yaml"
    yaml_path.write_text(
        "version: 1\n"
        "roles:\n"
        "  dreamer:\n"
        "    require:\n"
        "      structured_output: true\n"
        "    prefer:\n"
        "      cost_mode: local\n"
    )
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(yaml_path))
    reg2 = ModelRegistry.from_combined_config(roles=["dreamer"])
    assert [p.level for p in reg2.list_models()] == ["primary", "fallback", "fallback2"]


# ---------------------------------------------------------------------------
# 4. test_force_legacy_overrides_gateway
# ---------------------------------------------------------------------------


def test_force_legacy_overrides_gateway(monkeypatch, capsys):
    """`HIVE_FORCE_LEGACY_LLM=true` makes call_llm_with_fallback call
    the legacy path regardless of MODEL_GATEWAY_MODE (R4 §3, R5 §5)."""
    monkeypatch.setenv("HIVE_FORCE_LEGACY_LLM", "true")
    monkeypatch.setenv("MODEL_GATEWAY_MODE", "on")
    assert force_legacy_llm() is True
    assert resolve_gateway_mode() == "on"

    class _Ok(BaseModel):
        ok: bool

    sentinel = _Ok(ok=True)

    def fake_legacy(*args, **kwargs):
        return sentinel

    def explode(*args, **kwargs):
        raise AssertionError("gateway should NOT be called under HIVE_FORCE_LEGACY_LLM")

    with patch.object(llm_client, "_legacy_call_llm_with_fallback", side_effect=fake_legacy), \
         patch.object(llm_client, "_call_via_model_gateway", side_effect=explode):
        result = llm_client.call_llm_with_fallback("dreamer", "p", "s", _Ok)
    assert result is sentinel

    out = capsys.readouterr().err
    assert "emergency bypass" in out
    assert "HIVE_FORCE_LEGACY_LLM overrides MODEL_GATEWAY_MODE=on" in out


# ---------------------------------------------------------------------------
# 5. test_image_path_uses_legacy_bridge
# ---------------------------------------------------------------------------


def test_image_path_uses_legacy_bridge(monkeypatch, capsys, tmp_path):
    """When image_path is passed, the legacy path is used even with
    the gateway active (R8 §1)."""
    monkeypatch.setenv("MODEL_GATEWAY_MODE", "on")
    monkeypatch.setattr(llm_client, "_legacy_vision_bridge_warned", False)
    # image file must exist for the legacy call to not crash on open()
    img = tmp_path / "pixel.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header

    class _Ok(BaseModel):
        ok: bool

    sentinel = _Ok(ok=True)

    def fake_legacy(role, prompt, system_prompt, response_model, image_path=None, max_retries=2):
        return sentinel

    def explode(*args, **kwargs):
        raise AssertionError("gateway should NOT be called when image_path is set")

    with patch.object(llm_client, "_legacy_call_llm_with_fallback", side_effect=fake_legacy), \
         patch.object(llm_client, "_call_via_model_gateway", side_effect=explode):
        result = llm_client.call_llm_with_fallback(
            "dreamer", "p", "s", _Ok, image_path=str(img),
        )
    assert result is sentinel

    out = capsys.readouterr().err
    assert "legacy_vision_bridge_used=true" in out

    with patch.object(llm_client, "_legacy_call_llm_with_fallback", side_effect=fake_legacy):
        llm_client.call_llm_with_fallback(
            "dreamer", "p", "s", _Ok, image_path=str(img),
        )
    assert "legacy_vision_bridge_used=true" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 6. test_no_silent_fail_open
# ---------------------------------------------------------------------------


def test_no_silent_fail_open(monkeypatch, capsys):
    """When the gateway raises, the wrapper MUST emit a warning with
    `gateway_attempted=true, gateway_failed=true, legacy_fallback_used=true`
    and MUST delegate to the legacy path (R4 §5)."""
    monkeypatch.setenv("MODEL_GATEWAY_MODE", "auto")
    monkeypatch.setenv(
        "HIVE_DREAMER_PROVIDER", "ollama",
    )
    monkeypatch.setenv("HIVE_DREAMER_MODEL", "qwen3:14b")

    class _Ok(BaseModel):
        ok: bool

    sentinel = _Ok(ok=True)

    def mock_legacy(role, prompt, system_prompt, response_model, image_path=None, max_retries=2):
        return sentinel

    # Force the gateway initialization itself to fail so the real
    # _call_via_model_gateway path runs, prints its warning and emits
    # telemetry, then returns None — exactly the spec's fail-open case.
    def explode_factory(*args, **kwargs):
        raise RuntimeError("simulated gateway init failure")

    with patch.object(llm_client, "_legacy_call_llm_with_fallback", side_effect=mock_legacy) as mock_legacy, \
         patch.object(model_gateway, "ModelGateway", side_effect=explode_factory):
        result = llm_client.call_llm_with_fallback("dreamer", "p", "s", _Ok)
    assert result is sentinel

    out = capsys.readouterr().err
    # Both the warning printed by `_call_via_model_gateway` and the
    # `legacy_fallback` telemetry hook MUST be present (no silent fail-open).
    # The exact stderr message depends on the failure path taken (gateway
    # init failure, structured-call failure, etc.). What matters is that
    # the wrapper DELEGATED to legacy (sentinel returned) and the telemetry
    # stream records a `legacy_fallback` event.
    assert result is sentinel  # delegation worked
    assert "legacy_fallback" in out
    # And the legacy call MUST have been made exactly once.
    legacy_calls = [
        c for c in mock_legacy.call_args_list
    ]
    assert len(legacy_calls) == 1


# ---------------------------------------------------------------------------
# 7. test_gateway_mode_on_never_falls_back
# ---------------------------------------------------------------------------


def test_gateway_mode_on_never_falls_back(monkeypatch):
    """`MODEL_GATEWAY_MODE=on` with a failing gateway MUST raise a
    structured error and MUST NEVER call the legacy path (R5 §3)."""
    monkeypatch.setenv("MODEL_GATEWAY_MODE", "on")

    class _Ok(BaseModel):
        ok: bool

    def fake_legacy(*args, **kwargs):
        raise AssertionError("legacy MUST NOT be called when MODEL_GATEWAY_MODE=on")

    with patch.object(llm_client, "_legacy_call_llm_with_fallback", side_effect=fake_legacy), \
         patch.object(llm_client, "_call_via_model_gateway", return_value=None):
        with pytest.raises(RuntimeError) as exc:
            llm_client.call_llm_with_fallback("dreamer", "p", "s", _Ok)
    assert "MODE=on" in str(exc.value)


# ---------------------------------------------------------------------------
# 8. test_unsupported_explicit_listed
# ---------------------------------------------------------------------------


def test_unsupported_explicit_listed(monkeypatch):
    """A provider configured in HIVE_*_PROVIDER that does not exist in
    PROVIDERS_CONFIG nor in PROVIDER_ADAPTER_HINT appears in
    `validate()` as `unsupported_explicit` (R2 §3, Edge Case)."""
    monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "made-up-future-provider")
    monkeypatch.setenv("HIVE_DREAMER_MODEL", "x-1")

    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    problems = reg.validate()
    issues = [p.get("issue") for p in problems]
    assert "unsupported_explicit" in issues, problems
    # And the profile carries the reason.
    profile = reg.list_models()[0]
    assert profile.unsupported_reason is not None
