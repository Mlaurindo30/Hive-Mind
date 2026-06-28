"""K0 — aceite real do stack de embedding (docs/12 §K0).

- Dimensão 1024 com o modelo unificado (Ollama, requires_service).
- Migração CRR-safe aplicada: `workspace_id` + colunas de federação/provenance
  presentes num DB real inicializado pelo caminho de produção.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.real


@pytest.mark.requires_service("ollama")
def test_embedding_dim_1024(ollama_or_skip):
    """O embedder ativo produz vetores de 1024d (snowflake-arctic-embed2)."""
    from core.database import embed_text

    vec = embed_text("teste de embedding multilíngue em português e english")
    assert isinstance(vec, list)
    assert len(vec) == 1024, f"esperado 1024d, veio {len(vec)}"


def test_default_embedding_model_unified():
    """database.py e o worker sqlite-vec defaultam o MESMO modelo (mesma coleção,
    mesmo espaço vetorial). Sem serviço — inspeção de source (o worker tem
    side-effect de import: exige CLAUDE_MEM_DB, então não o executamos)."""
    from pathlib import Path

    import core.database as db

    assert db.OLLAMA_EMBED_MODEL == "snowflake-arctic-embed2:latest"

    worker_src = (Path(db.SINAPSE_HOME) / "plugins" / "sqlite-vec-worker"
                  / "worker.py").read_text()
    assert (
        'OLLAMA_EMBED_MODEL", "snowflake-arctic-embed2:latest"' in worker_src
    ), "worker e core devem defaultar o mesmo modelo de embedding"


def test_real_db_has_workspace_and_federation(real_db):
    """DB inicializado pelo caminho real tem as colunas da migração K0/B1."""
    cols = {r[1] for r in real_db.execute("PRAGMA table_info(neurons)")}
    assert "workspace_id" in cols
    assert {"origin_instance", "origin_signature",
            "embedding_model", "embedding_dim"} <= cols
