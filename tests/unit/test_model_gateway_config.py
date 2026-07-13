"""
tests/unit/test_model_gateway_config.py — config/model-gateway.yaml,
gateway_enabled() env flag, and ModelGateway.from_config().

Spec: specs/model-gateway.md Requirements 18-21, 30-31.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.model_gateway import ModelGateway, ModelGatewayError, gateway_enabled
from core.model_registry import ModelRegistryError

CONFIG_PATH = _PROJECT_ROOT / "config" / "model-gateway.yaml"


def test_shipped_config_exists_and_is_valid():
    assert CONFIG_PATH.is_file()
    gateway = ModelGateway.from_config(str(CONFIG_PATH))
    assert gateway.registry.validate() == []


def test_shipped_config_has_the_four_documented_example_profiles():
    gateway = ModelGateway.from_config(str(CONFIG_PATH))
    ids = {m.id for m in gateway.registry.list_models()}
    for expected in ("existing-dreamer", "lmstudio-local-json", "llamacpp-local", "litellm-proxy"):
        assert expected in ids


@pytest.mark.parametrize("value,expected", [
    # "true"/"1"/"yes" (any case) map to MODEL_GATEWAY_MODE=on -> enabled.
    ("true", True), ("1", True), ("yes", True), ("TRUE", True),
    # "false"/"0"/"no" map to MODEL_GATEWAY_MODE=off -> disabled.
    ("false", False), ("0", False),
    # Anything else (including "") doesn't match either legacy branch, so
    # resolve_gateway_mode() falls through to its "auto" default, which
    # gateway_enabled() treats as enabled (see resolve_gateway_mode docstring).
    ("", True),
])
def test_gateway_enabled_env_flag(monkeypatch, value, expected):
    monkeypatch.delenv("MODEL_GATEWAY_MODE", raising=False)
    monkeypatch.delenv("HIVE_FORCE_LEGACY_LLM", raising=False)
    monkeypatch.setenv("MODEL_GATEWAY_ENABLED", value)
    assert gateway_enabled() is expected


def test_gateway_enabled_defaults_true_when_unset(monkeypatch):
    # Unset -> resolve_gateway_mode() defaults to "auto", which
    # gateway_enabled() treats as enabled (gateway is tried first, with
    # fallback to legacy on failure -- see core/llm_client.py).
    monkeypatch.delenv("MODEL_GATEWAY_ENABLED", raising=False)
    monkeypatch.delenv("MODEL_GATEWAY_MODE", raising=False)
    monkeypatch.delenv("HIVE_FORCE_LEGACY_LLM", raising=False)
    assert gateway_enabled() is True


def test_from_config_missing_path_raises(tmp_path):
    with pytest.raises(ModelRegistryError):
        ModelGateway.from_config(str(tmp_path / "nope.yaml"))


def test_gateway_resolve_profile_requires_role_or_model_id():
    gateway = ModelGateway.from_config(str(CONFIG_PATH))
    with pytest.raises(ModelGatewayError):
        gateway._resolve_profile(None, None, None, None)


def test_gateway_resolve_profile_by_model_id_directly():
    gateway = ModelGateway.from_config(str(CONFIG_PATH))
    profile = gateway._resolve_profile(None, "existing-dreamer", None, None)
    assert profile.id == "existing-dreamer"
