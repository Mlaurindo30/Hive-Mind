"""Read-only HTTP loopback for the daemon (spec §15.1, §15.4).

Exactly three read routes, bound to loopback, no TLS, no auth, no write body:

  - GET /health  -> {"state", "services", "jobs"}
  - GET /ready   -> 200 if every required service is healthy, else 503
  - GET /metrics -> Prometheus-style counters

Mutations never live here (spec §15.4): start/stop/restart/reload/run-job go
through the authenticated control socket, not HTTP. The route allow-list is a
tested invariant (`READ_ONLY_HTTP_ROUTES`).

State is read from `state_dir/services.shadow.json` (written by the
ShadowSupervisor). Reading is pure; this module never mutates anything.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Response

READ_ONLY_HTTP_ROUTES = {"/health", "/ready", "/metrics"}

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 37780

SHADOW_STATE_FILENAME = "services.shadow.json"


def _read_state(state_dir: Path) -> dict | None:
    path = state_dir / SHADOW_STATE_FILENAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def create_app(state_dir: Path | str) -> FastAPI:
    """Build the read-only daemon HTTP app. No lifespan, no background work."""
    state_path = Path(state_dir)
    app = FastAPI(
        title="hive-mindd",
        description="Read-only daemon status surface (loopback).",
        version="1",
    )

    @app.get("/health")
    def health() -> dict:
        state = _read_state(state_path)
        if state is None:
            return {"state": "unknown", "services": {}, "jobs": {}}
        services = {
            s["name"]: s.get("readiness", "unknown")
            for s in state.get("services", [])
        }
        overall = "healthy" if state.get("ready") else "degraded"
        return {"state": overall, "services": services, "jobs": {}}

    @app.get("/ready")
    def ready(response: Response) -> dict:
        state = _read_state(state_path)
        # Fail-closed: no observation yet, or required services not ready => 503.
        is_ready = bool(state and state.get("ready"))
        response.status_code = 200 if is_ready else 503
        return {"ready": is_ready}

    @app.get("/metrics")
    def metrics() -> Response:
        state = _read_state(state_path) or {}
        services = state.get("services", [])
        ready_count = sum(1 for s in services if s.get("readiness") == "ready")
        lines = [
            "# HELP hive_service_count Number of observed services.",
            "# TYPE hive_service_count gauge",
            f"hive_service_count {len(services)}",
            "# HELP hive_service_ready Number of services observed ready.",
            "# TYPE hive_service_ready gauge",
            f"hive_service_ready {ready_count}",
            "# HELP hive_daemon_ready 1 if all required services are ready.",
            "# TYPE hive_daemon_ready gauge",
            f"hive_daemon_ready {1 if state.get('ready') else 0}",
        ]
        return Response("\n".join(lines) + "\n", media_type="text/plain")

    return app
