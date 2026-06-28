"""Fixtures da frente de conhecimento (tests/real) — backends reais, sem mock.

Regra (docs/12 §K9): aceite de fase K* = teste real verde. Testes que dependem
de serviço externo (Ollama/Milvus/FalkorDB) PULAM automaticamente quando o
serviço está offline (marker `requires_service`), nunca falham por ambiente.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.real.service_registry import check_service

ROOT = Path(__file__).resolve().parents[2]


def pytest_runtest_setup(item):
    for mark in item.iter_markers("requires_service"):
        from tests.real.service_registry import marker_services

        for service in marker_services(mark.args, mark.kwargs):
            status = check_service(service)
            if status.unknown:
                pytest.fail(status.reason)
            if not status.ok:
                pytest.skip(f"{status.reason} (requires_service:{status.name})")


@pytest.fixture
def ollama_or_skip() -> str:
    """Retorna a base do Ollama ou pula o teste se offline."""
    status = check_service("ollama")
    if not status.ok:
        pytest.skip(f"{status.reason} (requires_service:ollama)")
    import os
    return os.environ.get("OLLAMA_BASE", "http://localhost:11434")


@pytest.fixture
def real_db(tmp_path, monkeypatch):
    """SQLite real (sqlite-vec carregado) com schema + migrações da frente K.

    Usa o caminho de init real (`init_db` → `ensure_migrations`), apontado para
    um arquivo temporário. Sem CRDT (HIVE_CRDT_SYNC off) — a tabela nasce normal.
    """
    import core.database as db

    p = tmp_path / "hive_mind.db"
    monkeypatch.setattr(db, "DB_PATH", str(p))
    db.init_db()
    conn = db.get_connection()
    db.ensure_migrations(conn)
    yield conn
    conn.close()
