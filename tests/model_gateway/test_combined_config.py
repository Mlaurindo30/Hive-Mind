"""D2 — Coverage tests for ModelRegistry.from_combined_config and
build_profile_from_provider.

The bar is ≥ 80% line coverage on those two call paths in
`core.model_registry`. Coverage is measured by the CI runner via
`pytest --cov=core.model_registry`; this file only exists to drive
the high-coverage behaviour explicitly so the spec's intent is
visible in the test catalogue.
"""
from __future__ import annotations

import pytest

from core.auth import PROVIDERS_CONFIG
from core.model_registry import (
    PROVIDER_ADAPTER_HINT,
    ModelRegistry,
    ModelRegistryError,
)


def test_build_profile_basic_provider(dreamer_env):
    p = ModelRegistry.build_profile_from_provider("dreamer", "ollama", "qwen3:14b")
    assert p.role == "dreamer"
    assert p.level == "primary"
    assert p.provider == "openai_compatible"
    assert p.endpoint == PROVIDERS_CONFIG["ollama"]["base_url"]
    assert p.api_key_env == PROVIDERS_CONFIG["ollama"]["env_var"]
    assert "ollama" in p.auth_type or "local" in p.auth_type


def test_build_profile_unknown_provider_marks_unsupported():
    """A provider outside PROVIDERS_CONFIG and without an adapter mapping
    produces a profile with `unsupported_reason` set (R2 §3, Edge Case
    `unsupported_explicit`). It does NOT raise — the registry surfaces
    the issue via `validate()` instead of dropping the profile silently."""
    p = ModelRegistry.build_profile_from_provider("dreamer", "made-up", "x-1")
    assert p.unsupported_reason is not None
    assert p.role == "dreamer"


def test_build_profile_empty_role_raises():
    with pytest.raises(ModelRegistryError):
        ModelRegistry.build_profile_from_provider("", "ollama", "x")


def test_build_profile_empty_model_raises():
    with pytest.raises(ModelRegistryError):
        ModelRegistry.build_profile_from_provider("dreamer", "ollama", "")


def test_from_legacy_roles_only_dreamer(dreamer_env):
    reg = ModelRegistry.from_legacy_roles(roles=["dreamer"])
    assert len(reg.list_models()) == 3
    assert [p.level for p in reg.list_models()] == ["primary", "fallback", "fallback2"]


def test_from_legacy_roles_no_fallbacks(monkeypatch):
    # Clear any fallback env vars left over from a previous test that
    # called `load_env()` (e.g. the real-model-gateway test) so the
    # `from_legacy_roles` call sees only the primary we set here.
    for k in (
        "HIVE_VISION_FALLBACK_PROVIDER", "HIVE_VISION_FALLBACK_MODEL",
        "HIVE_VISION_FALLBACK2_PROVIDER", "HIVE_VISION_FALLBACK2_MODEL",
        "HIVE_DREAMER_FALLBACK_PROVIDER", "HIVE_DREAMER_FALLBACK_MODEL",
        "HIVE_DREAMER_FALLBACK2_PROVIDER", "HIVE_DREAMER_FALLBACK2_MODEL",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HIVE_VISION_PROVIDER", "ollama")
    monkeypatch.setenv("HIVE_VISION_MODEL", "llava")
    reg = ModelRegistry.from_legacy_roles(roles=["vision"])
    levels = [p.level for p in reg.list_models()]
    assert levels == ["primary"]


def test_from_combined_config_yaml_overrides_provider(dreamer_env, tmp_path, monkeypatch):
    """The `providers:` block in YAML overrides cost_mode and
    capabilities but NEVER provider identity or model name."""
    yaml_path = tmp_path / "model-gateway.yaml"
    yaml_path.write_text(
        "version: 1\n"
        "providers:\n"
        "  ollama:\n"
        "    cost_mode: local\n"
        "    capabilities:\n"
        "      chat: true\n"
        "      structured_output: true\n"
        "      embeddings: true\n"
        "      vision: true\n"
    )
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(yaml_path))

    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    primary = next(p for p in reg.list_models() if p.level == "primary")
    # Provider/model come from .env, NOT from YAML.
    assert primary.id.startswith("dreamer/ollama/")
    assert primary.model == "qwen3:14b"
    assert primary.cost_mode == "local"
    assert primary.capabilities.embeddings is True
    assert primary.capabilities.vision is True


def test_from_combined_config_role_override_warning(dreamer_env, tmp_path, monkeypatch, caplog):
    """provider/model in `roles:` block emit a warning and are ignored
    unless `role_override: true` (R7 §3)."""
    yaml_path = tmp_path / "model-gateway.yaml"
    yaml_path.write_text(
        "version: 1\n"
        "roles:\n"
        "  dreamer:\n"
        "    provider: someone-else\n"
        "    model: not-allowed\n"
    )
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(yaml_path))

    with caplog.at_level("WARNING"):
        reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    primary = next(p for p in reg.list_models() if p.level == "primary")
    # Still uses the .env value, not the YAML one.
    assert primary.model == "qwen3:14b"
    assert any("overlaps with .env" in r.message for r in caplog.records)


def test_from_combined_config_role_override_explicit(dreamer_env, tmp_path, monkeypatch):
    """`role_override: true` enables the YAML provider/model to take
    effect (R7 §3 — explicit override path)."""
    yaml_path = tmp_path / "model-gateway.yaml"
    yaml_path.write_text(
        "version: 1\n"
        "roles:\n"
        "  dreamer:\n"
        "    role_override: true\n"
        "    provider: openai\n"
        "    model: gpt-4o\n"
    )
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(yaml_path))

    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    primary = next(p for p in reg.list_models() if p.level == "primary")
    assert primary.model == "gpt-4o"
    assert "openai" in primary.id


def test_from_combined_config_no_yaml_works(dreamer_env, monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(tmp_path / "absent.yaml"))
    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    assert len(reg.list_models()) == 3


def test_validate_clean(dreamer_env, tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(tmp_path / "absent.yaml"))
    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    assert reg.validate() == []


def test_validate_unsupported_explicit(monkeypatch):
    monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "totally-unknown")
    monkeypatch.setenv("HIVE_DREAMER_MODEL", "x")
    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    problems = reg.validate()
    assert any(p.get("issue") == "unsupported_explicit" for p in problems)


def test_resolve_adapter_hint_every_known_provider():
    for provider in PROVIDER_ADAPTER_HINT:
        hint, reason = ModelRegistry.resolve_adapter_hint(provider)
        assert hint is not None
        assert reason is None
