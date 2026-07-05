from __future__ import annotations

import pytest

pytestmark = pytest.mark.real

"""Model Gateway — real LiteLLM proxy backend (HTTP proxy mode only).

Spec: specs/model-gateway.md D15, §10.3, § Out of Scope (direct-SDK mode).

SKIPs with an explicit reason when no LiteLLM proxy is reachable — never a
false pass. To exercise for real: `litellm --config litellm-config.yaml`,
then set LITELLM_BASE_URL/LITELLM_API_KEY, and enable the `litellm-proxy`
profile in config/model-gateway.yaml.
"""
import os
import socket
from urllib.parse import urlparse

from core.model_gateway import ModelGateway

BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000/v1")


def _reachable(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 4000
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def gateway():
    if not _reachable(BASE_URL):
        pytest.skip(f"LiteLLM proxy not reachable at {BASE_URL} (litellm --config ...)")
    gateway = ModelGateway.from_config()
    profile = gateway.registry.get("litellm-proxy")
    if not profile.enabled:
        pytest.skip("litellm-proxy profile is disabled in config/model-gateway.yaml")
    return gateway


def test_litellm_health(gateway):
    health = gateway.health()
    detail = next((d for d in health["details"] if d["provider"] == "litellm"), None)
    assert detail is not None
    assert detail["healthy"] is True


def test_litellm_chat(gateway):
    resp = gateway.chat(messages=[{"role": "user", "content": "Reply with PONG"}],
                          model_id="litellm-proxy")
    assert resp.ok is True, resp.error


def test_litellm_structured_output(gateway):
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    resp = gateway.structured(
        messages=[{"role": "user", "content": 'Return {"ok": true}'}], schema=schema,
        model_id="litellm-proxy",
    )
    assert resp.ok is True, resp.error


def test_litellm_secret_never_appears_in_error_on_failure(gateway):
    """If auth fails, the configured LITELLM_API_KEY must never leak into the error."""
    api_key = os.environ.get("LITELLM_API_KEY", "")
    resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], model_id="litellm-proxy")
    if resp.error and api_key:
        assert api_key not in resp.error
