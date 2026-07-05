"""
tests/unit/test_model_registry.py — Capability Registry (Priority 1).

Spec: specs/model-gateway.md Requirements 1-6, Edge Cases 1-5, 25-28.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.model_registry import (
    GatewayDefaults,
    ModelCapabilities,
    ModelNotFoundError,
    ModelProfile,
    ModelRegistry,
    ModelRegistryError,
    NoModelForRoleError,
    UnknownCapabilityError,
)


def _profile(**overrides) -> ModelProfile:
    defaults = dict(
        id="m1", provider="native", model="x", roles=["validator"], priority=100,
    )
    defaults.update(overrides)
    return ModelProfile(**defaults)


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "model-gateway.yaml"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def test_registry_loads_valid_yaml(tmp_path):
    path = _write_yaml(tmp_path, """
version: 1
defaults:
  timeout_s: 45
models:
  - id: a
    provider: native
    model: x
    roles: [dreamer]
""")
    registry = ModelRegistry.from_yaml(path)
    assert [m.id for m in registry.list_models()] == ["a"]
    assert registry.defaults.timeout_s == 45


def test_registry_missing_file_raises(tmp_path):
    with pytest.raises(ModelRegistryError):
        ModelRegistry.from_yaml(tmp_path / "does-not-exist.yaml")


def test_registry_malformed_yaml_raises(tmp_path):
    path = _write_yaml(tmp_path, "models: [{id: a, provider: [unterminated")
    with pytest.raises(ModelRegistryError):
        ModelRegistry.from_yaml(path)


def test_registry_env_vars_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_TEST_MODEL", "real-model")
    path = _write_yaml(tmp_path, """
version: 1
models:
  - id: a
    provider: native
    model: "${MG_TEST_MODEL}"
    endpoint: "${MG_TEST_ENDPOINT:-http://localhost:9/v1}"
    roles: [dreamer]
""")
    registry = ModelRegistry.from_yaml(path)
    profile = registry.get("a")
    assert profile.model == "real-model"
    assert profile.endpoint == "http://localhost:9/v1"


def test_registry_unset_env_var_uses_default(tmp_path, monkeypatch):
    monkeypatch.delenv("MG_UNSET_VAR", raising=False)
    path = _write_yaml(tmp_path, """
version: 1
models:
  - id: a
    provider: native
    model: "${MG_UNSET_VAR:-fallback-model}"
    roles: [dreamer]
""")
    registry = ModelRegistry.from_yaml(path)
    assert registry.get("a").model == "fallback-model"


def test_registry_duplicate_model_id_raises(tmp_path):
    path = _write_yaml(tmp_path, """
version: 1
models:
  - id: dup
    provider: native
    model: x
    roles: [a]
  - id: dup
    provider: native
    model: y
    roles: [b]
""")
    with pytest.raises(ModelRegistryError, match="duplicate"):
        ModelRegistry.from_yaml(path)


def test_registry_unknown_provider_raises(tmp_path):
    path = _write_yaml(tmp_path, """
version: 1
models:
  - id: a
    provider: not-a-real-provider
    model: x
    roles: [a]
""")
    with pytest.raises(ModelRegistryError, match="unknown provider"):
        ModelRegistry.from_yaml(path)


# ---------------------------------------------------------------------------
# get() / list_models()
# ---------------------------------------------------------------------------

def test_get_returns_profile():
    registry = ModelRegistry([_profile(id="a"), _profile(id="b")])
    assert registry.get("a").id == "a"


def test_get_unknown_id_raises():
    registry = ModelRegistry([_profile(id="a")])
    with pytest.raises(ModelNotFoundError):
        registry.get("nope")


def test_list_models_preserves_config_order():
    registry = ModelRegistry([_profile(id="z"), _profile(id="a"), _profile(id="m")])
    assert [m.id for m in registry.list_models()] == ["z", "a", "m"]


# ---------------------------------------------------------------------------
# select()
# ---------------------------------------------------------------------------

def test_select_disabled_model_not_selected():
    registry = ModelRegistry([
        _profile(id="disabled", enabled=False, roles=["validator"], priority=1),
        _profile(id="enabled", enabled=True, roles=["validator"], priority=99),
    ])
    assert registry.select("validator").id == "enabled"


def test_select_model_without_required_capability_not_selected():
    registry = ModelRegistry([
        _profile(id="plain", roles=["validator"], priority=1,
                 capabilities=ModelCapabilities(structured_output=False)),
        _profile(id="structured", roles=["validator"], priority=99,
                 capabilities=ModelCapabilities(structured_output=True)),
    ])
    picked = registry.select("validator", require={"structured_output": True})
    assert picked.id == "structured"


def test_select_unknown_role_raises_clear_error():
    registry = ModelRegistry([_profile(id="a", roles=["validator"])])
    with pytest.raises(NoModelForRoleError):
        registry.select("no-such-role")


def test_select_unknown_capability_raises():
    registry = ModelRegistry([_profile(id="a")])
    with pytest.raises(UnknownCapabilityError):
        registry.select("validator", require={"telepathy": True})


def test_select_respects_fallback_chain_role():
    registry = ModelRegistry([
        _profile(id="fb", roles=["fallback"]),
    ])
    # no model tagged 'validator' -> falls back to a model tagged 'fallback'
    assert registry.select("validator").id == "fb"


def test_select_lower_priority_number_wins():
    registry = ModelRegistry([
        _profile(id="low-prio-number", roles=["validator"], priority=5),
        _profile(id="high-prio-number", roles=["validator"], priority=50),
    ])
    assert registry.select("validator").id == "low-prio-number"


def test_select_prefer_local_picks_cost_mode_local():
    registry = ModelRegistry([
        _profile(id="paid", roles=["validator"], priority=10, cost_mode="paid"),
        _profile(id="local", roles=["validator"], priority=10, cost_mode="local"),
    ])
    picked = registry.select("validator", prefer={"cost_mode": "local"})
    assert picked.id == "local"


def test_select_structured_output_requires_flag():
    registry = ModelRegistry([
        _profile(id="a", roles=["validator"],
                 capabilities=ModelCapabilities(structured_output=False)),
    ])
    with pytest.raises(NoModelForRoleError):
        registry.select("validator", require={"structured_output": True})


def test_select_tool_calling_requires_flag():
    registry = ModelRegistry([_profile(id="a", roles=["validator"])])
    with pytest.raises(NoModelForRoleError):
        registry.select("validator", require={"tool_calling": True})


def test_select_vision_requires_flag():
    registry = ModelRegistry([_profile(id="a", roles=["validator"])])
    with pytest.raises(NoModelForRoleError):
        registry.select("validator", require={"vision": True})


def test_select_embeddings_requires_flag():
    registry = ModelRegistry([_profile(id="a", roles=["validator"])])
    with pytest.raises(NoModelForRoleError):
        registry.select("validator", require={"embeddings": True})


def test_select_rerank_requires_flag():
    registry = ModelRegistry([_profile(id="a", roles=["validator"])])
    with pytest.raises(NoModelForRoleError):
        registry.select("validator", require={"rerank": True})


def test_select_model_with_empty_roles_not_selected_by_role():
    registry = ModelRegistry([_profile(id="no-roles", roles=[])])
    with pytest.raises(NoModelForRoleError):
        registry.select("validator")
    # still directly addressable
    assert registry.get("no-roles").id == "no-roles"


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------

def test_validate_clean_config_returns_empty():
    registry = ModelRegistry([_profile(id="a", roles=["validator"])])
    assert registry.validate() == []


def test_validate_flags_missing_roles():
    registry = ModelRegistry([_profile(id="a", roles=[])])
    problems = registry.validate()
    assert any(p["issue"] == "no_roles" for p in problems)


def test_validate_flags_paid_without_cost_fields():
    registry = ModelRegistry([_profile(id="a", roles=["x"], cost_mode="paid")])
    problems = registry.validate()
    assert any(p["issue"] == "paid_without_cost_fields" for p in problems)


def test_validate_flags_missing_fallback_target():
    registry = ModelRegistry([_profile(id="a", roles=["x"], fallback_chain=["ghost"])])
    problems = registry.validate()
    assert any(p["issue"] == "fallback_target_missing" for p in problems)


def test_validate_never_raises_on_dirty_config():
    registry = ModelRegistry([
        _profile(id="a", roles=[], cost_mode="paid", fallback_chain=["ghost"]),
    ])
    problems = registry.validate()
    assert len(problems) >= 2
