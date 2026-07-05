from __future__ import annotations

import pytest

pytestmark = pytest.mark.real

"""Model Gateway — real LM Studio backend.

Spec: specs/model-gateway.md D15, §10.3.

SKIPs with an explicit reason when LM Studio's server is not running or has
no model loaded — never a false pass. To exercise this for real:
  lms get <model>   # download at least one model
  lms server start  # or: lms load <model> --gpu max
Then set LMSTUDIO_BASE_URL if it differs from the default.
"""
import os
import socket
from urllib.parse import urlparse

from core.model_gateway import ModelGateway

BASE_URL = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")


def _reachable(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 1234
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def gateway():
    if not _reachable(BASE_URL):
        pytest.skip(f"LM Studio server not reachable at {BASE_URL} (lms server start)")
    return ModelGateway.from_config()


def test_lmstudio_health(gateway):
    health = gateway.health()
    detail = next((d for d in health["details"] if d["provider"] == "lmstudio"), None)
    if detail is None:
        pytest.skip("no lmstudio profile enabled in config/model-gateway.yaml")
    assert detail["healthy"] is True


def test_lmstudio_chat(gateway):
    resp = gateway.chat(messages=[{"role": "user", "content": "Reply with PONG"}], role="validator",
                          model_id="lmstudio-local-json")
    assert resp.ok is True, resp.error


def test_lmstudio_structured_output(gateway):
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    resp = gateway.structured(
        messages=[{"role": "user", "content": 'Return {"ok": true}'}], schema=schema,
        model_id="lmstudio-local-json",
    )
    assert resp.ok is True, resp.error


def test_lmstudio_tool_calling_capability_declared(gateway):
    profile = gateway.registry.get("lmstudio-local-json")
    assert profile.capabilities.tool_calling is True
