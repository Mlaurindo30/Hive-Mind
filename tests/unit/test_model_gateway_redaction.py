"""
tests/unit/test_model_gateway_redaction.py — no secret ever reaches
ModelResponse.error, model_telemetry, or an adapter exception message.

Spec: specs/model-gateway.md Requirement 27, Edge Case 8, 20.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core import model_telemetry
from core.model_gateway import ModelGateway, ModelResponse
from core.model_registry import ModelCapabilities, ModelProfile, ModelRegistry

FAKE_SECRET = "sk-proj-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"


def test_adapter_exception_containing_secret_is_redacted():
    registry = ModelRegistry([
        ModelProfile(id="a", provider="native", model="x", roles=["validator"]),
    ])
    gateway = ModelGateway(registry)

    class LeakyAdapter:
        def chat(self, profile, messages, **kwargs):
            raise RuntimeError(f"upstream rejected credential {FAKE_SECRET}")

    with patch("core.model_gateway._adapter_for", return_value=LeakyAdapter()):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")

    assert resp.ok is False
    assert FAKE_SECRET not in resp.error
    assert "[REDACTED" in resp.error


def test_adapter_returned_error_string_containing_secret_is_redacted():
    registry = ModelRegistry([
        ModelProfile(id="a", provider="native", model="x", roles=["validator"]),
    ])
    gateway = ModelGateway(registry)

    class LeakyAdapter:
        def chat(self, profile, messages, **kwargs):
            return ModelResponse(
                ok=False, content=None, model_id=profile.id, provider=profile.provider,
                endpoint=profile.endpoint, latency_ms=1.0, input_tokens=None, output_tokens=None,
                cost_estimate=None, fallback_used=False, fallback_chain=[],
                error=f"auth_error: api_key={FAKE_SECRET}",
            )

    with patch("core.model_gateway._adapter_for", return_value=LeakyAdapter()):
        resp = gateway.chat(messages=[{"role": "user", "content": "hi"}], role="validator")

    assert FAKE_SECRET not in resp.error


def test_model_telemetry_record_call_has_no_prompt_parameter():
    import inspect
    sig = inspect.signature(model_telemetry.record_call)
    for banned in ("prompt", "content", "response", "messages", "payload"):
        assert banned not in sig.parameters, f"record_call must never accept a {banned!r} field"


def test_model_telemetry_redacts_endpoint_and_error_type(capsys):
    record = model_telemetry.record_call(
        request_id="r1", workspace_id="default", role="validator",
        selected_model_id="a", provider="openai_compatible",
        endpoint="http://api.example.com/v1", capabilities_required={},
        fallback_used=False, latency_ms=1.0, input_tokens=1, output_tokens=1,
        cost_estimate=None, error_type=f"auth_error token={FAKE_SECRET}",
    )
    assert FAKE_SECRET not in record["error_type"]
    captured = capsys.readouterr()
    assert FAKE_SECRET not in captured.err


def test_structured_bad_schema_error_does_not_leak_secret_from_content():
    registry = ModelRegistry([
        ModelProfile(id="a", provider="native", model="x", roles=["validator"],
                     capabilities=ModelCapabilities(structured_output=True)),
    ])
    gateway = ModelGateway(registry)

    class SecretLeakingAdapter:
        def structured(self, profile, messages, schema, **kwargs):
            return ModelResponse(
                ok=True, content={"leaked": FAKE_SECRET}, model_id=profile.id,
                provider=profile.provider, endpoint=profile.endpoint, latency_ms=1.0,
                input_tokens=1, output_tokens=1, cost_estimate=None, fallback_used=False,
                fallback_chain=[], error=None,
            )

    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    with patch("core.model_gateway._adapter_for", return_value=SecretLeakingAdapter()):
        resp = gateway.structured(messages=[{"role": "user", "content": "hi"}], schema=schema, role="validator")
    # schema_invalid because 'answer' is missing — the error string itself must not carry the secret
    assert resp.ok is False
    assert FAKE_SECRET not in resp.error
