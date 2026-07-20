"""D007 (fatia 2) — read-only HTTP loopback (spec §15.1, §15.4).

The daemon's HTTP surface is read-only: /health, /ready, /metrics. Any
mutation route (POST/PUT/DELETE, or a path outside the allow-list) is a
contract violation. Bind is loopback-only; no TLS, no auth, no write body.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hive_mind.daemon.http_api import READ_ONLY_HTTP_ROUTES, create_app


def _shadow_state(state_dir: Path, ready: bool = True) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "services.shadow.json").write_text(
        json.dumps(
            {
                "mode": "shadow",
                "profile": "local-min",
                "service_count": 2,
                "ready": ready,
                "services": [
                    {"name": "db", "required": True,
                     "readiness": "ready" if ready else "not_ready"},
                    {"name": "api", "required": False, "readiness": "ready"},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_only_read_only_routes_are_exposed(tmp_path):
    app = create_app(state_dir=tmp_path)
    allowed = READ_ONLY_HTTP_ROUTES | {"/docs", "/openapi.json", "/docs/oauth2-redirect", "/redoc"}
    for route in app.routes:
        path = getattr(route, "path", None)
        if path is None or path in allowed:
            continue
        pytest.fail(f"unexpected HTTP route exposed by the daemon: {path}")


def test_no_mutating_http_methods(tmp_path):
    app = create_app(state_dir=tmp_path)
    for route in app.routes:
        methods = getattr(route, "methods", set()) or set()
        mutating = methods & {"POST", "PUT", "DELETE", "PATCH"}
        assert not mutating, f"{route.path} exposes mutating methods {mutating}"


def test_health_reports_services(tmp_path):
    _shadow_state(tmp_path)
    client = TestClient(create_app(state_dir=tmp_path))
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] in {"healthy", "degraded"}
    assert "db" in body["services"]
    assert "jobs" in body


def test_ready_returns_200_when_required_ready(tmp_path):
    _shadow_state(tmp_path, ready=True)
    client = TestClient(create_app(state_dir=tmp_path))
    assert client.get("/ready").status_code == 200


def test_ready_returns_503_when_required_not_ready(tmp_path):
    _shadow_state(tmp_path, ready=False)
    client = TestClient(create_app(state_dir=tmp_path))
    assert client.get("/ready").status_code == 503


def test_ready_returns_503_when_no_state_yet(tmp_path):
    client = TestClient(create_app(state_dir=tmp_path))
    # No shadow pass has run: fail-closed, not fail-open.
    assert client.get("/ready").status_code == 503


def test_metrics_is_prometheus_text(tmp_path):
    _shadow_state(tmp_path)
    client = TestClient(create_app(state_dir=tmp_path))
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "hive_service_count" in resp.text


def test_post_to_health_is_405_or_404(tmp_path):
    client = TestClient(create_app(state_dir=tmp_path))
    assert client.post("/health").status_code in (404, 405)


def test_no_start_stop_reload_routes(tmp_path):
    client = TestClient(create_app(state_dir=tmp_path))
    for path in ("/start", "/stop", "/restart", "/reload", "/run-job"):
        assert client.post(path).status_code == 404
