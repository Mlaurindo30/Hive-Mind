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
    ("true", True), ("1", True), ("yes", True), ("TRUE", True),
    ("false", False), ("0", False), ("", False),
])
def test_gateway_enabled_env_flag(monkeypatch, value, expected):
    monkeypatch.setenv("MODEL_GATEWAY_ENABLED", value)
    assert gateway_enabled() is expected


def test_gateway_enabled_defaults_false_when_unset(monkeypatch):
    monkeypatch.delenv("MODEL_GATEWAY_ENABLED", raising=False)
    assert gateway_enabled() is False


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
