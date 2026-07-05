"""
tests/unit/test_model_gateway_response_contract.py — ModelResponse /
EmbeddingResponse / RerankResponse dataclass shape and the JSON-Schema ->
Pydantic validation bridge.

Spec: specs/model-gateway.md Requirement 9, 12; Edge Cases 16-17.
"""
from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.model_gateway import (
    EmbeddingResponse,
    ModelResponse,
    RerankResponse,
    json_schema_to_model,
    validate_against_schema,
)

_MODEL_RESPONSE_FIELDS = {
    "ok", "content", "model_id", "provider", "endpoint", "latency_ms",
    "input_tokens", "output_tokens", "cost_estimate", "fallback_used",
    "fallback_chain", "error", "raw", "error_chain",
}


def test_model_response_has_exactly_the_spec_fields():
    actual = {f.name for f in fields(ModelResponse)}
    assert actual == _MODEL_RESPONSE_FIELDS


def test_model_response_ok_true_instance():
    resp = ModelResponse(ok=True, content="hi", model_id="m", provider="native",
                          endpoint=None, latency_ms=1.0, input_tokens=1, output_tokens=1,
                          cost_estimate=None, fallback_used=False, fallback_chain=[], error=None)
    assert resp.ok is True
    assert resp.error is None


def test_embedding_response_shape():
    resp = EmbeddingResponse(ok=True, vectors=[[0.1, 0.2]], model_id="m", provider="native",
                              endpoint=None, latency_ms=1.0)
    assert resp.vectors == [[0.1, 0.2]]
    assert resp.error is None


def test_rerank_response_shape():
    resp = RerankResponse(ok=True, results=[{"index": 0, "relevance_score": 0.9}],
                           model_id="m", provider="native", endpoint=None, latency_ms=1.0)
    assert resp.results[0]["relevance_score"] == 0.9


# ---------------------------------------------------------------------------
# json_schema_to_model / validate_against_schema
# ---------------------------------------------------------------------------

def test_schema_to_model_flat_object():
    schema = {"type": "object", "properties": {
        "name": {"type": "string"}, "age": {"type": "integer"},
    }, "required": ["name"]}
    model_cls = json_schema_to_model("T", schema)
    instance = model_cls(name="a")
    assert instance.name == "a"
    assert instance.age is None
    with pytest.raises(Exception):
        model_cls()  # missing required 'name'


def test_schema_to_model_rejects_non_object_top_level():
    with pytest.raises(ValueError):
        json_schema_to_model("T", {"type": "array"})


def test_validate_against_schema_accepts_matching_content():
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    valid, reason = validate_against_schema({"answer": "42"}, schema)
    assert valid is True
    assert reason is None


def test_validate_against_schema_rejects_missing_required_field():
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    valid, reason = validate_against_schema({"other": 1}, schema)
    assert valid is False
    assert reason is not None


def test_validate_against_schema_rejects_non_dict_content():
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    valid, reason = validate_against_schema("not a dict", schema)
    assert valid is False
    assert "object" in reason


def test_validate_against_schema_json_valid_but_wrong_type():
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}
    valid, reason = validate_against_schema({"count": "not-an-int"}, schema)
    assert valid is False
