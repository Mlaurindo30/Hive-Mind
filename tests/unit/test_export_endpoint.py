"""
Tests for POST /api/v1/neurons/export (Sprint D1 — Federated Swarm HM-12).
Uses FastAPI TestClient with a patched in-memory SQLite connection.
"""
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Load sinapse-api.py module (hyphenated filename) without importing it as a
# top-level module, so we can control env vars before it resolves the API key.
# ---------------------------------------------------------------------------
_API_KEY = "test-api-key-sprint-d1"

_api_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "sinapse-api.py"


def _inject_stubs():
    """Inject lightweight stubs for optional heavy dependencies not installed in the test env."""
    # slowapi stub
    if "slowapi" not in sys.modules:
        slowapi_stub = MagicMock()
        slowapi_stub.Limiter = MagicMock(return_value=MagicMock(limit=lambda *a, **k: (lambda f: f)))
        slowapi_stub._rate_limit_exceeded_handler = MagicMock()
        slowapi_stub.util = MagicMock(get_remote_address=MagicMock())
        slowapi_stub.errors = MagicMock(RateLimitExceeded=Exception)
        sys.modules["slowapi"] = slowapi_stub
        sys.modules["slowapi.util"] = slowapi_stub.util
        sys.modules["slowapi.errors"] = slowapi_stub.errors

    # cryptography.fernet stub (may or may not be present)
    if "cryptography" not in sys.modules:
        crypto_stub = MagicMock()
        sys.modules["cryptography"] = crypto_stub
        sys.modules["cryptography.fernet"] = crypto_stub.fernet

    # core.database stub — prevents real DB connection during module load
    if "core.database" not in sys.modules:
        db_stub = MagicMock()
        sys.modules["core"] = MagicMock()
        sys.modules["core.database"] = db_stub


def _load_api_module():
    """Load the FastAPI app with all required env vars set."""
    os.environ.setdefault("HIVE_MIND_API_KEY", _API_KEY)
    os.environ.setdefault("HIVE_MIND_MASTER_KEY", "dmVyeWxvbmdtYXN0ZXJrZXlmb3J0ZXN0aW5nMTIzNDU2Nzg=")
    _inject_stubs()
    spec = importlib.util.spec_from_file_location("sinapse_api", _api_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Minimal in-memory SQLite schema
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE neurons (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    type TEXT NOT NULL,
    source_file TEXT,
    content TEXT,
    hash TEXT,
    metadata JSON,
    community INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    visibility TEXT DEFAULT 'private',
    indexed_at TIMESTAMP
);
"""


def _make_conn(rows=None):
    """Return an in-memory sqlite3.Connection with optional seed rows.
    check_same_thread=False is required because FastAPI TestClient runs in a different thread.
    """
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    if rows:
        for r in rows:
            conn.execute(
                "INSERT INTO neurons (id, label, type, visibility, metadata) VALUES (?, ?, ?, ?, ?)",
                (
                    r["id"],
                    r["label"],
                    r["type"],
                    r["visibility"],
                    r.get("metadata"),
                ),
            )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api_mod(monkeypatch=None):
    os.environ["HIVE_MIND_API_KEY"] = _API_KEY
    os.environ["HIVE_MIND_MASTER_KEY"] = "dmVyeWxvbmdtYXN0ZXJrZXlmb3J0ZXN0aW5nMTIzNDU2Nzg="
    return _load_api_module()


@pytest.fixture(scope="module")
def client(api_mod):
    from fastapi.testclient import TestClient
    return TestClient(api_mod.app, raise_server_exceptions=True)


def _auth_headers():
    return {"Authorization": f"Bearer {_API_KEY}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExportEndpoint:

    def test_export_requires_auth(self, client):
        """No API key must return 401."""
        resp = client.post("/api/v1/neurons/export", json={})
        assert resp.status_code == 401

    def test_export_returns_only_shared_public(self, api_mod, client):
        """Only neurons with visibility 'shared' or 'public' are exported."""
        rows = [
            {"id": "n1", "label": "private-node", "type": "fact", "visibility": "private"},
            {"id": "n2", "label": "shared-node", "type": "fact", "visibility": "shared"},
            {"id": "n3", "label": "public-node", "type": "fact", "visibility": "public"},
        ]
        conn = _make_conn(rows)
        with patch.object(api_mod, "get_connection", return_value=conn):
            resp = client.post(
                "/api/v1/neurons/export",
                json={"redact": False},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["count"] == 2
        ids = {n["id"] for n in data["neurons"]}
        assert ids == {"n2", "n3"}

    def test_export_filters_by_type(self, api_mod, client):
        """Filter by type returns only matching neurons."""
        rows = [
            {"id": "f1", "label": "fact-node", "type": "fact", "visibility": "shared"},
            {"id": "p1", "label": "pref-node", "type": "preference", "visibility": "shared"},
        ]
        conn = _make_conn(rows)
        with patch.object(api_mod, "get_connection", return_value=conn):
            resp = client.post(
                "/api/v1/neurons/export",
                json={"filters": {"type": "fact"}, "redact": False},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["neurons"][0]["id"] == "f1"

    def test_export_does_not_relay_federated_neurons(self, api_mod, client):
        rows = [
            {
                "id": "local",
                "label": "local",
                "type": "fact",
                "visibility": "shared",
            },
            {
                "id": "federated:peer:n1",
                "label": "relayed",
                "type": "fact",
                "visibility": "shared",
                "metadata": json.dumps({"federated": True}),
            },
        ]
        conn = _make_conn(rows)
        with patch.object(api_mod, "get_connection", return_value=conn):
            resp = client.post(
                "/api/v1/neurons/export",
                json={"redact": False},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200
        assert [item["id"] for item in resp.json()["neurons"]] == ["local"]

    def test_export_redact_called(self, api_mod, client):
        """redact_neuron must be called once per exported neuron when redact=True."""
        rows = [
            {"id": "r1", "label": "redact-me", "type": "fact", "visibility": "shared"},
            {"id": "r2", "label": "also-redact", "type": "fact", "visibility": "public"},
        ]
        conn = _make_conn(rows)
        mock_redact = MagicMock(side_effect=lambda n: n)
        fake_redactor = MagicMock()
        fake_redactor.redact_neuron = mock_redact

        with patch.object(api_mod, "get_connection", return_value=conn):
            with patch.dict("sys.modules", {"core.redactor": fake_redactor}):
                resp = client.post(
                    "/api/v1/neurons/export",
                    json={"redact": True},
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        assert mock_redact.call_count == 2

    def test_export_sign_called_when_requested(self, api_mod, client):
        """sign_neuron must be called once per exported neuron when sign=True."""
        rows = [
            {"id": "s1", "label": "sign-me", "type": "fact", "visibility": "shared"},
        ]
        conn = _make_conn(rows)
        mock_sign = MagicMock(side_effect=lambda n, k: {**n, "_signature": "sig", "_pubkey_fingerprint": "fp"})
        fake_signing = MagicMock()
        fake_signing.sign_neuron = mock_sign

        with patch.object(api_mod, "get_connection", return_value=conn):
            with patch.dict("sys.modules", {"core.signing": fake_signing, "core.redactor": MagicMock(redact_neuron=lambda n: n)}):
                resp = client.post(
                    "/api/v1/neurons/export",
                    json={"sign": True, "redact": True},
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        data = resp.json()
        assert mock_sign.call_count == 1
        assert data["neurons"][0]["_signature"] == "sig"

    def test_export_fails_closed_when_redaction_fails(self, api_mod, client):
        rows = [
            {"id": "r1", "label": "secret", "type": "fact", "visibility": "shared"},
        ]
        conn = _make_conn(rows)
        fake_redactor = MagicMock()
        fake_redactor.redact_neuron.side_effect = RuntimeError("redactor unavailable")

        with patch.object(api_mod, "get_connection", return_value=conn):
            with patch.dict("sys.modules", {"core.redactor": fake_redactor}):
                resp = client.post(
                    "/api/v1/neurons/export",
                    json={"redact": True},
                    headers=_auth_headers(),
                )

        assert resp.status_code == 500
        assert "redactor unavailable" in resp.json()["detail"]
        assert "neurons" not in resp.json()

    def test_export_fails_closed_when_signing_fails(self, api_mod, client):
        rows = [
            {"id": "s1", "label": "shared", "type": "fact", "visibility": "shared"},
        ]
        conn = _make_conn(rows)
        fake_signing = MagicMock()
        fake_signing.sign_neuron.side_effect = FileNotFoundError("private key missing")
        fake_redactor = MagicMock(redact_neuron=lambda neuron: neuron)

        with patch.object(api_mod, "get_connection", return_value=conn):
            with patch.dict(
                "sys.modules",
                {"core.signing": fake_signing, "core.redactor": fake_redactor},
            ):
                resp = client.post(
                    "/api/v1/neurons/export",
                    json={"sign": True, "redact": True},
                    headers=_auth_headers(),
                )

        assert resp.status_code == 500
        assert "private key missing" in resp.json()["detail"]
        assert "neurons" not in resp.json()
