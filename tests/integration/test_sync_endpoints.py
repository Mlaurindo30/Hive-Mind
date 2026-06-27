"""Integração: endpoints HTTP de sync CRDT (P8 — Bloco D).

Valida o caminho HTTP real de /api/v1/sync/export e /import com FastAPI
TestClient, contra DBs CR-SQLite temporários (não o banco real). Cobre:
  - enforcement de auth (sem token → 401/403)
  - gate HIVE_CRDT_SYNC (503 quando desabilitado)
  - round-trip export→import preservando PK e propagando UPDATE

Autocontido: não depende de HIVE_RUN_INTEGRATION nem do hive_mind.db real.
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "integrations" / "crsqlite"

pytestmark = pytest.mark.skipif(
    not (VENDOR / "crsqlite.so").exists()
    and not (VENDOR / "crsqlite.dylib").exists()
    and not (VENDOR / "crsqlite.dll").exists(),
    reason="CR-SQLite nao baixado. Rode install.sh (secao CR-SQLite).",
)

pytest.importorskip("fastapi")
pytest.importorskip("slowapi")
pytest.importorskip("cryptography")

# Chave + flag definidas ANTES de carregar a API (lidas no import/handlers).
API_KEY = "sync_endpoint_test_key_456"
os.environ["HIVE_MIND_API_KEY"] = API_KEY
os.environ["HIVE_CRDT_SYNC"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(ROOT))

_api_script = ROOT / "scripts" / "services" / "sinapse-api.py"
_spec = importlib.util.spec_from_file_location("sinapse_api", _api_script)
api_mod = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(api_mod)
except ImportError as exc:
    pytest.skip(f"Dependência da API ausente: {exc}", allow_module_level=True)

client = TestClient(api_mod.app)
_AUTH = {"Authorization": f"Bearer {API_KEY}"}


@pytest.fixture(autouse=True)
def _ensure_api_key(monkeypatch):
    # test_sinapse_api também seta HIVE_MIND_API_KEY no import com OUTRA chave;
    # a API lê a chave por request, então reafirmamos a chave DESTE módulo antes
    # de cada teste (monkeypatch restaura ao final).
    monkeypatch.setenv("HIVE_MIND_API_KEY", API_KEY)


SCHEMA = """
CREATE TABLE neurons (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    score REAL DEFAULT 0.0
);
"""


def _make_crr_db(path: str) -> None:
    import sqlite_vec
    from integrations.crsqlite import client as crdt
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.executescript(SCHEMA)
    crdt.enable_crdt(conn)
    crdt.finalize(conn)
    conn.close()


def _open_crr(path: str) -> sqlite3.Connection:
    import sqlite_vec
    from integrations.crsqlite import client as crdt
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    crdt.load_crsqlite_extension(conn)
    return conn


def test_sync_export_requires_auth():
    r = client.get("/api/v1/sync/export")
    assert r.status_code in (401, 403)


def test_sync_import_requires_auth():
    r = client.post("/api/v1/sync/import", json={"changes": []})
    assert r.status_code in (401, 403)


def test_sync_export_503_when_disabled(monkeypatch):
    """Sem HIVE_CRDT_SYNC=true, o endpoint recusa com 503."""
    monkeypatch.delenv("HIVE_CRDT_SYNC", raising=False)
    r = client.get("/api/v1/sync/export", headers=_AUTH)
    assert r.status_code == 503


def test_sync_roundtrip_preserves_pk_and_update(monkeypatch, tmp_path):
    """export(A) → import(B) via HTTP: PK íntegra e UPDATE propaga."""
    import core.database as db
    from integrations.crsqlite import client as crdt

    a_path = str(tmp_path / "a.db")
    b_path = str(tmp_path / "b.db")
    _make_crr_db(a_path)
    _make_crr_db(b_path)

    # A cria neuron com id legível.
    a = _open_crr(a_path)
    a.execute("INSERT INTO neurons (id,label,score) VALUES ('http-n1','v1',0.5)")
    a.commit()
    crdt.finalize(a)
    a.close()

    # GET /sync/export apontando DB_PATH para A.
    monkeypatch.setattr(db, "DB_PATH", a_path)
    r = client.get("/api/v1/sync/export?since=0", headers=_AUTH)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert len(payload["changes"]) >= 2

    # POST /sync/import apontando DB_PATH para B.
    monkeypatch.setattr(db, "DB_PATH", b_path)
    r = client.post("/api/v1/sync/import", json=payload, headers=_AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["applied"] >= 2

    # B tem o neuron com ID correto (não pk binário corrompido).
    b = _open_crr(b_path)
    row = b.execute("SELECT id, label, score FROM neurons").fetchone()
    crdt.finalize(b)
    b.close()
    assert row is not None and row[0] == "http-n1" and row[1] == "v1"

    # UPDATE em A propaga para B via novo round-trip.
    a = _open_crr(a_path)
    a.execute("UPDATE neurons SET label='v2', score=0.9 WHERE id='http-n1'")
    a.commit()
    crdt.finalize(a)
    a.close()

    monkeypatch.setattr(db, "DB_PATH", a_path)
    payload2 = client.get("/api/v1/sync/export?since=0", headers=_AUTH).json()
    monkeypatch.setattr(db, "DB_PATH", b_path)
    client.post("/api/v1/sync/import", json=payload2, headers=_AUTH)

    b = _open_crr(b_path)
    row = b.execute("SELECT label, score FROM neurons WHERE id='http-n1'").fetchone()
    crdt.finalize(b)
    b.close()
    assert row == ("v2", 0.9), f"update não propagou via HTTP: {row}"
