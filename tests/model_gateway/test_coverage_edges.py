"""Additional coverage tests for the Model Gateway unification, focused
on the error paths and edge cases in `from_combined_config`,
`build_profile_from_provider`, and the registry validation. D2 requires
≥80% line coverage in those two functions specifically.
"""
from __future__ import annotations

import pytest

from core.model_registry import (
    GatewayDefaults,
    ModelRegistry,
    ModelRegistryError,
)


def test_from_yaml_missing_file_raises(tmp_path):
    with pytest.raises(ModelRegistryError, match="not found"):
        ModelRegistry.from_yaml(tmp_path / "nope.yaml")


def test_from_yaml_malformed_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("models: [unclosed")
    with pytest.raises(ModelRegistryError, match="failed to parse"):
        ModelRegistry.from_yaml(str(bad))


def test_from_yaml_non_mapping_top_level_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n")
    with pytest.raises(ModelRegistryError, match="expected a YAML mapping"):
        ModelRegistry.from_yaml(str(bad))


def test_from_yaml_missing_id_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 1\n"
        "models:\n"
        "  - provider: native\n"
        "    model: x\n"
    )
    with pytest.raises(ModelRegistryError, match="missing required 'id'"):
        ModelRegistry.from_yaml(str(bad))


def test_from_yaml_unknown_provider_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 1\n"
        "models:\n"
        "  - id: bad\n"
        "    provider: not-real\n"
        "    model: x\n"
    )
    with pytest.raises(ModelRegistryError, match="unknown provider"):
        ModelRegistry.from_yaml(str(bad))


def test_from_yaml_duplicate_id_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "version: 1\n"
        "models:\n"
        "  - id: dup\n"
        "    provider: native\n"
        "    model: x\n"
        "  - id: dup\n"
        "    provider: native\n"
        "    model: y\n"
    )
    with pytest.raises(ModelRegistryError, match="duplicate model id"):
        ModelRegistry.from_yaml(str(bad))


def test_validate_paid_without_cost_fields(dreamer_env, monkeypatch, tmp_path):
    """Setting `cost_mode: paid` on a profile without cost fields MUST
    surface as `paid_without_cost_fields` in `validate()`."""
    yaml_path = tmp_path / "model-gateway.yaml"
    yaml_path.write_text(
        "version: 1\n"
        "providers:\n"
        "  openai:\n"
        "    cost_mode: paid\n"
    )
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(yaml_path))
    monkeypatch.setenv("HIVE_DREAMER_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("HIVE_DREAMER_FALLBACK_MODEL", "gpt-4o-mini")
    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    problems = reg.validate()
    assert any(p.get("issue") == "paid_without_cost_fields" for p in problems)


def test_validate_unknown_provider(dreamer_env, monkeypatch, tmp_path):
    """An unknown runtime provider on a legacy profile triggers the
    `unknown_provider` diagnostic."""
    # Hack: build a profile manually with a provider not in _KNOWN_PROVIDERS.
    from core.model_registry import ModelProfile, ModelCapabilities
    reg = ModelRegistry([
        ModelProfile(
            id="manual/bad",
            provider="definitely-not-a-real-adapter",  # type: ignore[arg-type]
            model="x",
            role="manual",
            level="primary",
            capabilities=ModelCapabilities(),
        )
    ])
    problems = reg.validate()
    assert any(p.get("issue") == "unknown_provider" for p in problems)


def test_validate_fallback_target_missing(dreamer_env, monkeypatch, tmp_path):
    """A profile whose `fallback_chain` references an id not in the
    registry triggers `fallback_target_missing`."""
    from core.model_registry import ModelProfile, ModelCapabilities
    reg = ModelRegistry([
        ModelProfile(
            id="primary",
            provider="native",
            model="x",
            role="dreamer",
            level="primary",
            capabilities=ModelCapabilities(),
            fallback_chain=["nonexistent"],
        )
    ])
    problems = reg.validate()
    assert any(p.get("issue") == "fallback_target_missing" for p in problems)


def test_build_profile_sets_legacy_provider(dreamer_env):
    """`ModelProfile.legacy_provider` is set to the original provider
    name (e.g. `ollama`), distinct from `provider` (the runtime adapter
    `openai_compatible`)."""
    p = ModelRegistry.build_profile_from_provider("dreamer", "ollama", "qwen3:14b")
    assert p.legacy_provider == "ollama"
    assert p.provider == "openai_compatible"


def test_build_profile_unsupported_keeps_legacy_provider():
    """A profile built for an unknown provider still carries the
    `legacy_provider` name so the operator can see what was attempted."""
    p = ModelRegistry.build_profile_from_provider("dreamer", "future-llm", "x-1")
    assert p.legacy_provider == "future-llm"
    assert p.unsupported_reason is not None


def test_from_combined_config_yaml_invalid_raises(monkeypatch, tmp_path):
    """A broken YAML is reported as `ModelRegistryError` by
    `from_combined_config`."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("models: [unclosed")
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(bad))
    monkeypatch.setenv("HIVE_DREAMER_PROVIDER", "ollama")
    monkeypatch.setenv("HIVE_DREAMER_MODEL", "qwen3:14b")
    with pytest.raises(ModelRegistryError):
        ModelRegistry.from_combined_config(roles=["dreamer"])


def test_from_combined_config_role_override_priority(dreamer_env, tmp_path, monkeypatch):
    """Priority and other role-only fields in YAML are applied to the
    matching profile."""
    yaml_path = tmp_path / "model-gateway.yaml"
    yaml_path.write_text(
        "version: 1\n"
        "roles:\n"
        "  dreamer:\n"
        "    priority: 5\n"
        "    cost_mode: local\n"
        "    context_window: 8192\n"
    )
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(yaml_path))
    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    primary = next(p for p in reg.list_models() if p.level == "primary")
    assert primary.priority == 5
    assert primary.cost_mode == "local"
    assert primary.context_window == 8192


def test_from_combined_config_defaults_via_yaml(dreamer_env, tmp_path, monkeypatch):
    """When the YAML has a `defaults:` block, those fields populate
    `ModelRegistry.defaults` (only relevant for the YAML-only
    `from_yaml` path; in the combined path the legacy wins, but the
    parser must not crash)."""
    yaml_path = tmp_path / "model-gateway.yaml"
    yaml_path.write_text(
        "version: 1\n"
        "defaults:\n"
        "  timeout_s: 30\n"
        "  max_retries: 3\n"
        "  fallback_enabled: false\n"
    )
    monkeypatch.setenv("MODEL_GATEWAY_CONFIG", str(yaml_path))
    reg = ModelRegistry.from_combined_config(roles=["dreamer"])
    assert isinstance(reg.defaults, GatewayDefaults)
