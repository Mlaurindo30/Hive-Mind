"""
tests/unit/test_model_adapters_contract.py — HTTP contract tests for
OpenAICompatibleAdapter (shared by openai_compatible/lmstudio/llamacpp/
vllm/sglang/litellm). Mocks `requests` — this is a protocol/contract test,
not real-backend evidence (see tests/real/ for that).

Spec: specs/model-gateway.md § 10.2, Edge Cases 6-17.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.model_registry import ModelCapabilities, ModelProfile
from integrations.model_gateway.openai_compatible_adapter import OpenAICompatibleAdapter


def _profile(**overrides) -> ModelProfile:
    defaults = dict(
        id="m1", provider="openai_compatible", model="test-model",
        endpoint="http://localhost:1234/v1", context_window=4096, max_output_tokens=100,
        roles=["validator"],
        capabilities=ModelCapabilities(chat=True, structured_output=True, embeddings=True, rerank=True),
    )
    defaults.update(overrides)
    return ModelProfile(**defaults)


def _mock_response(status_code=200, json_body=None, content_type="application/json"):
    resp = Mock()
    resp.status_code = status_code
    resp.headers = {"content-type": content_type}
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("no json")
    return resp


@pytest.fixture
def adapter():
    return OpenAICompatibleAdapter(provider="openai_compatible")


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------

def test_chat_success(adapter):
    body = {
        "choices": [{"message": {"role": "assistant", "content": "hi there"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    with patch("requests.post", return_value=_mock_response(200, body)):
        resp = adapter.chat(_profile(), [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is True
    assert resp.content == "hi there"
    assert resp.input_tokens == 3
    assert resp.output_tokens == 2


def test_chat_timeout(adapter):
    with patch("requests.post", side_effect=requests.exceptions.Timeout()):
        resp = adapter.chat(_profile(), [{"role": "user", "content": "hi"}], timeout_s=1)
    assert resp.ok is False
    assert resp.error == "timeout"


def test_chat_connection_refused(adapter):
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):
        resp = adapter.chat(_profile(), [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is False
    assert resp.error == "connection_refused"


def test_chat_auth_error_401(adapter):
    with patch("requests.post", return_value=_mock_response(401)):
        resp = adapter.chat(_profile(), [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is False
    assert resp.error == "auth_error"


def test_chat_auth_error_403(adapter):
    with patch("requests.post", return_value=_mock_response(403)):
        resp = adapter.chat(_profile(), [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.error == "auth_error"


def test_chat_rate_limited_429(adapter):
    with patch("requests.post", return_value=_mock_response(429)):
        resp = adapter.chat(_profile(), [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is False
    assert resp.error == "rate_limited"


def test_chat_backend_error_500(adapter):
    with patch("requests.post", return_value=_mock_response(500)):
        resp = adapter.chat(_profile(), [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is False
    assert "backend_error" in resp.error


def test_chat_html_instead_of_json(adapter):
    resp_mock = _mock_response(200, None, content_type="text/html")
    with patch("requests.post", return_value=resp_mock):
        resp = adapter.chat(_profile(), [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is False
    assert "malformed_response" in resp.error


def test_chat_json_without_choices(adapter):
    with patch("requests.post", return_value=_mock_response(200, {"no_choices_here": True})):
        resp = adapter.chat(_profile(), [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is False
    assert "no_choices" in resp.error


def test_chat_invalid_json_body(adapter):
    resp_mock = Mock(status_code=200, headers={"content-type": "application/json"})
    resp_mock.json.side_effect = ValueError("bad json")
    with patch("requests.post", return_value=resp_mock):
        resp = adapter.chat(_profile(), [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is False
    assert "invalid_json" in resp.error


def test_chat_clamps_max_tokens_to_profile_limit(adapter):
    body = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["max_tokens"] = json["max_tokens"]
        return _mock_response(200, body)

    with patch("requests.post", side_effect=fake_post):
        adapter.chat(_profile(max_output_tokens=50), [{"role": "user", "content": "hi"}],
                     max_tokens=99999, timeout_s=5)
    assert captured["max_tokens"] == 50


# ---------------------------------------------------------------------------
# structured()
# ---------------------------------------------------------------------------

def test_structured_success_parses_json_content(adapter):
    body = {"choices": [{"message": {"content": '{"answer": "42"}'}}], "usage": {}}
    with patch("requests.post", return_value=_mock_response(200, body)):
        resp = adapter.structured(_profile(), [{"role": "user", "content": "hi"}],
                                   {"type": "object"}, timeout_s=5)
    assert resp.ok is True
    assert resp.content == {"answer": "42"}


def test_structured_non_json_content_fails(adapter):
    body = {"choices": [{"message": {"content": "not json at all"}}], "usage": {}}
    with patch("requests.post", return_value=_mock_response(200, body)):
        resp = adapter.structured(_profile(), [{"role": "user", "content": "hi"}],
                                   {"type": "object"}, timeout_s=5)
    assert resp.ok is False
    assert resp.error == "structured_output_not_json"


# ---------------------------------------------------------------------------
# embed() / rerank()
# ---------------------------------------------------------------------------

def test_embed_success(adapter):
    body = {"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}
    with patch("requests.post", return_value=_mock_response(200, body)):
        resp = adapter.embed(_profile(), ["a", "b"], timeout_s=5)
    assert resp.ok is True
    assert resp.vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_unsupported_capability_returns_ok_false():
    profile = _profile(capabilities=ModelCapabilities(embeddings=False))
    adapter = OpenAICompatibleAdapter()
    resp = adapter.embed(profile, ["a"])
    assert resp.ok is False
    assert "capability_not_supported" in resp.error


def test_rerank_success(adapter):
    body = {"results": [{"index": 0, "relevance_score": 0.9}, {"index": 1, "relevance_score": 0.1}]}
    with patch("requests.post", return_value=_mock_response(200, body)):
        resp = adapter.rerank(_profile(), "query", ["doc1", "doc2"], timeout_s=5)
    assert resp.ok is True
    assert len(resp.results) == 2


def test_rerank_result_count_mismatch(adapter):
    body = {"results": [{"index": 0, "relevance_score": 0.9}]}  # only 1 result for 2 docs
    with patch("requests.post", return_value=_mock_response(200, body)):
        resp = adapter.rerank(_profile(), "query", ["doc1", "doc2"], timeout_s=5)
    assert resp.ok is False
    assert "result_count_mismatch" in resp.error


# ---------------------------------------------------------------------------
# health()
# ---------------------------------------------------------------------------

def test_health_reachable(adapter):
    with patch("requests.get", return_value=Mock(status_code=200)):
        result = adapter.health(_profile())
    assert result["healthy"] is True


def test_health_unreachable(adapter):
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError()):
        result = adapter.health(_profile())
    assert result["healthy"] is False


# ---------------------------------------------------------------------------
# Every backend family reuses the same class (Requirement 15)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Basic SSRF guard (specs/model-gateway.md § Out of Scope)
# ---------------------------------------------------------------------------

def test_blocks_file_scheme(adapter):
    profile = _profile(endpoint="file:///etc/passwd")
    resp = adapter.chat(profile, [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is False


def test_blocks_aws_metadata_ip(adapter):
    profile = _profile(endpoint="http://169.254.169.254/latest/meta-data")
    resp = adapter.chat(profile, [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is False


def test_blocks_gcp_metadata_hostname(adapter):
    profile = _profile(endpoint="http://metadata.google.internal/v1")
    resp = adapter.chat(profile, [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is False


def test_allows_localhost(adapter):
    body = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
    with patch("requests.post", return_value=_mock_response(200, body)):
        resp = adapter.chat(_profile(endpoint="http://127.0.0.1:1234/v1"),
                             [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is True


def test_warns_but_allows_0_0_0_0(adapter, capsys):
    body = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
    with patch("requests.post", return_value=_mock_response(200, body)):
        resp = adapter.chat(_profile(endpoint="http://0.0.0.0:1234/v1"),
                             [{"role": "user", "content": "hi"}], timeout_s=5)
    assert resp.ok is True
    assert "0.0.0.0" in capsys.readouterr().err


@pytest.mark.parametrize("module_path,class_name,expected_provider", [
    ("integrations.model_gateway.lmstudio_adapter", "LMStudioAdapter", "lmstudio"),
    ("integrations.model_gateway.llamacpp_adapter", "LlamaCppAdapter", "llamacpp"),
    ("integrations.model_gateway.vllm_adapter", "VLLMAdapter", "vllm"),
    ("integrations.model_gateway.sglang_adapter", "SGLangAdapter", "sglang"),
    ("integrations.model_gateway.litellm_adapter", "LiteLLMAdapter", "litellm"),
])
def test_backend_specific_adapters_are_openai_compatible_subclasses(module_path, class_name, expected_provider):
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    assert issubclass(cls, OpenAICompatibleAdapter)
    instance = cls()
    assert instance.provider == expected_provider
