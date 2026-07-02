"""K10 feature flag tests for sinapse-api workspace behavior.

Guarantees single-tenant default remains intact unless the flag is enabled.
"""

import os
from pathlib import Path
import importlib.util
from contextlib import contextmanager
from types import SimpleNamespace
from fastapi.testclient import TestClient


def _load_api_module(module_name="sinapse_api_flag_tests"):
    api_script = Path(__file__).resolve().parents[2] / "scripts" / "services" / "sinapse-api.py"
    spec = importlib.util.spec_from_file_location(module_name, api_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_multi_tenant_flag_defaults_disabled(monkeypatch):
    monkeypatch.delenv("HIVE_MULTI_TENANT_ENABLED", raising=False)
    api = _load_api_module()
    assert api._multi_tenant_enabled() is False


def test_multi_tenant_flag_truthy_values(monkeypatch):
    api = _load_api_module()
    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("HIVE_MULTI_TENANT_ENABLED", value)
        assert api._multi_tenant_enabled() is True


def test_multi_tenant_flag_falsy_values(monkeypatch):
    api = _load_api_module()
    for value in ("0", "false", "FALSE", "no", "off", ""):
        monkeypatch.setenv("HIVE_MULTI_TENANT_ENABLED", value)
        assert api._multi_tenant_enabled() is False


def test_query_endpoint_propagates_header_workspace_to_router(monkeypatch):
    monkeypatch.setenv("HIVE_MIND_API_KEY", "test-key")
    monkeypatch.setenv("HIVE_MULTI_TENANT_ENABLED", "true")
    api = _load_api_module()
    captured = {}

    def fake_route_query(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return {
            "answer_context": [{"id": "ctx-1", "content": "ok"}],
            "retrieval_path": [],
            "citations": [],
            "confidence": 1.0,
            "missing_context": [],
            "intent": "hybrid",
        }

    monkeypatch.setattr("core.retrieval.router.route_query", fake_route_query)
    monkeypatch.setattr(api, "_build_sinapse_query_fn", lambda: (lambda _q: {"source": "test"}))

    client = TestClient(api.app)
    response = client.post(
        "/api/v1/query",
        json={"query": "workspace route", "intent": "hybrid", "limit": 2},
        headers={"Authorization": "Bearer test-key", "X-Workspace-Id": "tenant-a"},
    )

    assert response.status_code == 200
    assert captured["query"] == "workspace route"
    assert captured["top_k"] == 2
    assert captured["intent"] == "hybrid"
    assert captured["workspace_id"] == "tenant-a"
    assert callable(captured["sinapse_query_fn"])


def test_workspaces_endpoint_stays_open_on_loopback(monkeypatch):
    monkeypatch.setenv("HIVE_MIND_API_HOST", "127.0.0.1")
    api = _load_api_module("sinapse_api_loopback_workspaces")
    assert api._workspaces_requires_auth() is False


def test_workspaces_endpoint_requires_auth_on_public_bind(monkeypatch):
    monkeypatch.setenv("HIVE_MIND_API_HOST", "0.0.0.0")
    api = _load_api_module("sinapse_api_public_workspaces")

    client = TestClient(api.app)
    response = client.get("/api/v1/workspaces")

    assert api._workspaces_requires_auth() is True
    assert response.status_code in {401, 403}


def test_rest_middleware_emits_trace_id_without_sensitive_attributes(monkeypatch):
    monkeypatch.setenv("HIVE_MIND_API_KEY", "test-key")
    monkeypatch.setenv("HIVE_MULTI_TENANT_ENABLED", "true")
    api = _load_api_module("sinapse_api_trace_tests")
    captured = {"span_name": None, "attributes": None, "set": {}}

    class FakeSpan:
        def get_span_context(self):
            return SimpleNamespace(trace_id=int("a" * 32, 16))

        def set_attribute(self, key, value):
            captured["set"][key] = value

    @contextmanager
    def fake_span(name, attributes):
        captured["span_name"] = name
        captured["attributes"] = dict(attributes)
        yield FakeSpan()

    monkeypatch.setattr(api, "span", fake_span)
    monkeypatch.setattr(api, "flush_telemetry", lambda: None)

    client = TestClient(api.app)
    response = client.get(
        "/api/v1/health",
        headers={
            "Authorization": "Bearer test-key",
            "X-Workspace-Id": "tenant-a",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Trace-Id"] == "a" * 32
    assert captured["span_name"] == "api./api/v1/health"
    assert captured["attributes"] == {
        "method": "GET",
        "path": "/api/v1/health",
        "workspace_id": "tenant-a",
    }
    assert captured["set"]["status_code"] == 200
    leaked_keys = set(captured["attributes"]) | set(captured["set"])
    assert not {"authorization", "token", "body", "content"} & {k.lower() for k in leaked_keys}
