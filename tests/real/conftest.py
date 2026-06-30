"""Fixtures da frente de conhecimento (tests/real) — backends reais, sem mock.

Regra (docs/12 §K9): aceite de fase K* = teste real verde. Testes que dependem
de serviço externo (Ollama/Milvus/FalkorDB/claude-mem) PULAM automaticamente quando o
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


@pytest.fixture
def milvus_or_skip() -> str:
    """Inicializa MilvusBackend real ou pula o teste se Milvus offline.

    Retorna o prefixo de coleção usado para isolar o teste de outros batches.
    Caller deve usar o prefixo ao construir `MilvusBackend(collection_prefix=...)`
    e limpar as coleções criadas (ver `milvus_backend`).
    """
    status = check_service("milvus")
    if not status.ok:
        pytest.skip(f"{status.reason} (requires_service:milvus)")
    import os
    import uuid
    return os.environ.get("MILVUS_URI", "http://localhost:19530"), f"hm_test_{uuid.uuid4().hex[:12]}_"


@pytest.fixture
def milvus_backend(milvus_or_skip):
    """`MilvusBackend` real apontando para Milvus online, com prefixo isolado.

    Faz teardown das coleções criadas pelo teste ao final.
    """
    from core.vector_backend import MilvusBackend

    uri, prefix = milvus_or_skip
    backend = MilvusBackend(uri=uri, collection_prefix=prefix)
    yield backend, prefix
    try:
        for collection in list(backend._client.list_collections()):
            if collection.startswith(prefix):
                backend._client.drop_collection(collection)
    except Exception:
        pass


@pytest.fixture
def claude_mem_or_skip(tmp_path, monkeypatch):
    """`claude-mem` real via SQLite temporário, sem worker HTTP.

    Cria um banco com a forma mínima esperada pelo bridge (observations,
    discoveries, session_summaries, user_prompts) em `tmp_path/claude-mem.db`
    e aponta `CLAUDE_MEM_DB` para ele. Pula se a dependência
    `claude_mem_bridge` não estiver acessível (import falho) — o que torna o
    fixture seguro em máquinas sem o pacote.
    """
    import sqlite3
    try:
        from core.knowledge import claude_mem_bridge as bridge
    except Exception as exc:  # pragma: no cover - depende do host
        pytest.skip(f"claude_mem_bridge indisponivel: {exc}")
    db = tmp_path / "claude-mem.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT NOT NULL,
            project TEXT NOT NULL,
            text TEXT,
            type TEXT NOT NULL,
            title TEXT,
            subtitle TEXT,
            facts TEXT,
            narrative TEXT,
            concepts TEXT,
            files_read TEXT,
            files_modified TEXT,
            prompt_number INTEGER,
            created_at TEXT,
            session_branch TEXT
        );
        CREATE TABLE discoveries (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT NOT NULL,
            project TEXT NOT NULL,
            text TEXT,
            type TEXT NOT NULL,
            title TEXT,
            subtitle TEXT,
            facts TEXT,
            narrative TEXT,
            concepts TEXT,
            files_read TEXT,
            files_modified TEXT,
            prompt_number INTEGER,
            created_at TEXT,
            session_branch TEXT
        );
        CREATE TABLE session_summaries (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT NOT NULL,
            project TEXT NOT NULL,
            created_at TEXT,
            request TEXT,
            investigated TEXT,
            learned TEXT,
            completed TEXT,
            next_steps TEXT,
            session_branch TEXT
        );
        CREATE TABLE user_prompts (
            id INTEGER PRIMARY KEY,
            memory_session_id TEXT NOT NULL,
            project TEXT NOT NULL,
            prompt TEXT,
            created_at TEXT,
            session_branch TEXT
        );
        CREATE INDEX idx_obs_project ON observations(project, created_at);
        CREATE INDEX idx_disc_project ON discoveries(project, created_at);
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("CLAUDE_MEM_DB", str(db))
    monkeypatch.setenv("CLAUDE_MEM_WORKER_HOST", "")
    yield bridge

@pytest.fixture
def falkordb_or_skip(monkeypatch) -> tuple[str, int, str]:
    """Retorna (host, port, database) do FalkorDB ou pula o teste se offline.

    Cada teste ganha um `FALKORDB_DB` proprio (`hm_test_<uuid12>`) via
    `monkeypatch.setenv`, isolando o namespace sem o caller precisar de
    `DETACH DELETE`. FalkorDB suporta multi-database, entao criar um DB
    novo por teste eh barato e seguro. No teardown o DB eh dropado e o
    env restaurado.

    Caller deve usar `graphiti_available()` (ou o modulo
    `integrations.graphiti`) para chamar o servico; o teste e considerado
    real apenas quando o servico responde ao TCP probe.
    """
    import os
    import uuid
    import falkordb

    status = check_service("falkordb")
    if not status.ok:
        pytest.skip(f"{status.reason} (requires_service:falkordb)")
    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = int(os.environ.get("FALKORDB_PORT", "6379"))
    database = f"hm_test_{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("FALKORDB_DB", database)

    # Limpa o singleton do Graphiti (se o teste anterior construiu um cliente
    # contra um DB diferente, o cache precisa ser invalidado).
    try:
        import integrations.graphiti as graphiti_module
        graphiti_module._graphiti = None
    except Exception:
        pass

    yield host, port, database

    # Teardown: dropa o DB unico e invalida o cache do Graphiti.
    try:
        client = falkordb.FalkorDB(host=host, port=port)
        try:
            client.delete_database(database)
        finally:
            client.close()
    except Exception:
        pass
    try:
        import integrations.graphiti as graphiti_module
        graphiti_module._graphiti = None
    except Exception:
        pass


@pytest.fixture
def ragflow_or_skip():
    """Importa o wrapper RAGFlow ou pula o teste se offline.

    Caller deve usar `RAGFlowSettings`, `assert_health` ou `create_client`
    do modulo `integrations.ragflow`. O servico so e considerado real
    quando responde em `/api/v1/health` ou `/`. Caso o modulo nao
    esteja instalado, pula explicito (RAGFlow e opcional no gate K9).
    """
    try:
        from integrations.ragflow import RAGFlowSettings, assert_health
    except Exception as exc:  # pragma: no cover - depende do host
        pytest.skip(f"integrations.ragflow indisponivel: {exc}")
    status = check_service("ragflow")
    if not status.ok:
        pytest.skip(f"{status.reason} (requires_service:ragflow)")
    return RAGFlowSettings, assert_health

