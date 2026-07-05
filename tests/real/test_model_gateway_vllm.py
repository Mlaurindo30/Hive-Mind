from __future__ import annotations

import pytest

pytestmark = pytest.mark.real

"""Model Gateway — real vLLM backend.

Spec: specs/model-gateway.md D15, §10.3.

SKIPs with an explicit reason when no vLLM server is reachable — never a
false pass. To exercise for real: `vllm serve <model>`, then set
VLLM_BASE_URL if it differs from the default, and enable the `vllm-local`
profile in config/model-gateway.yaml.
"""
import os
import socket
from urllib.parse import urlparse

from core.model_gateway import ModelGateway

BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")


def _reachable(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def gateway():
    if not _reachable(BASE_URL):
        pytest.skip(f"vLLM server not reachable at {BASE_URL} (vllm serve <model>)")
    gateway = ModelGateway.from_config()
    profile = gateway.registry.get("vllm-local")
    if not profile.enabled:
        pytest.skip("vllm-local profile is disabled in config/model-gateway.yaml")
    return gateway


def test_vllm_health(gateway):
    health = gateway.health()
    detail = next((d for d in health["details"] if d["provider"] == "vllm"), None)
    assert detail is not None
    assert detail["healthy"] is True


def test_vllm_chat(gateway):
    resp = gateway.chat(messages=[{"role": "user", "content": "Reply with PONG"}],
                          model_id="vllm-local")
    assert resp.ok is True, resp.error


def test_vllm_structured_output(gateway):
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    resp = gateway.structured(
        messages=[{"role": "user", "content": 'Return {"ok": true}'}], schema=schema,
        model_id="vllm-local",
    )
    assert resp.ok is True, resp.error
