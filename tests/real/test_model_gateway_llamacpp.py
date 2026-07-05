from __future__ import annotations

import pytest

pytestmark = pytest.mark.real

"""Model Gateway — real llama.cpp `server` backend.

Spec: specs/model-gateway.md D15, §10.3.

SKIPs with an explicit reason when no llama.cpp server is reachable — never
a false pass. To exercise for real: `llama-server -m <model.gguf> --port 8080`,
then set LLAMACPP_BASE_URL if it differs from the default.
"""
import os
import socket
from urllib.parse import urlparse

from core.model_gateway import ModelGateway

BASE_URL = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8080/v1")


def _reachable(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8080
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def gateway():
    if not _reachable(BASE_URL):
        pytest.skip(f"llama.cpp server not reachable at {BASE_URL} (llama-server -m <model.gguf>)")
    return ModelGateway.from_config()


def test_llamacpp_health(gateway):
    health = gateway.health()
    detail = next((d for d in health["details"] if d["provider"] == "llamacpp"), None)
    if detail is None:
        pytest.skip("no llamacpp profile enabled in config/model-gateway.yaml")
    assert detail["healthy"] is True


def test_llamacpp_chat(gateway):
    resp = gateway.chat(messages=[{"role": "user", "content": "Reply with PONG"}],
                          model_id="llamacpp-local")
    assert resp.ok is True, resp.error


def test_llamacpp_structured_output(gateway):
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    resp = gateway.structured(
        messages=[{"role": "user", "content": 'Return {"ok": true}'}], schema=schema,
        model_id="llamacpp-local",
    )
    assert resp.ok is True, resp.error


def test_llamacpp_embeddings(gateway):
    resp = gateway.embed(["hello world"], model_id="llamacpp-local")
    assert resp.ok is True, resp.error
    assert len(resp.vectors) == 1


def test_llamacpp_rerank(gateway):
    resp = gateway.rerank("query text", ["doc a", "doc b"], model_id="llamacpp-local")
    assert resp.ok is True, resp.error
    assert len(resp.results) == 2
