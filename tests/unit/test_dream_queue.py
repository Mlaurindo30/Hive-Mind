"""Testes de regressão da auditoria técnica (2026-06-10).

Cobre:
- Bug C3 (dream queue): filtro de observações arquivadas deve usar a coluna
  `archived` e não um LIKE sobre `metadata` (que exclui linhas com metadata NULL).
- Bug C1 (document_ingest): `doc_metadata` deve ser definido ANTES do seu uso
  no INSERT em document_memories dentro de run_ingestion().

Nenhum teste chama LLM nem depende do hive_mind.db real.
"""
import ast
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestArchivedFilterRegression:
    """Regressão do bug C3: observações com metadata NULL eram filtradas
    incorretamente pelo filtro antigo `metadata NOT LIKE '%"archived": true%'`."""

    def _make_db(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """CREATE TABLE observations (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                project TEXT,
                type TEXT,
                title TEXT,
                content TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                neuron_id TEXT,
                archived INTEGER DEFAULT 0,
                metadata JSON
            )"""
        )
        rows = [
            # (id, metadata, archived)
            ("obs-null-meta", None, 0),    # metadata NULL — o bug antigo a excluía
            ("obs-empty-meta", "{}", 0),   # metadata vazia
            ("obs-archived", "{}", 1),     # arquivada — deve ficar de fora
        ]
        for oid, meta, archived in rows:
            conn.execute(
                "INSERT INTO observations (id, session_id, project, type, title, "
                "content, neuron_id, archived, metadata) "
                "VALUES (?, 's1', 'hive-mind', 'note', 't', 'c', NULL, ?, ?)",
                (oid, archived, meta),
            )
        conn.commit()
        return conn

    def test_archived_column_filter_includes_null_metadata(self):
        conn = self._make_db()
        try:
            rows = conn.execute(
                "SELECT id FROM observations WHERE archived = 0"
            ).fetchall()
            ids = {r[0] for r in rows}
            assert ids == {"obs-null-meta", "obs-empty-meta"}, (
                "O filtro por coluna archived deve retornar exatamente as 2 "
                "observações não arquivadas, incluindo a de metadata NULL"
            )
        finally:
            conn.close()

    def test_old_metadata_like_filter_was_buggy(self):
        """Documenta o bug antigo: o LIKE sobre metadata exclui linhas NULL."""
        conn = self._make_db()
        try:
            rows = conn.execute(
                "SELECT id FROM observations "
                "WHERE metadata NOT LIKE '%\"archived\": true%'"
            ).fetchall()
            ids = {r[0] for r in rows}
            # NULL NOT LIKE ... => NULL (falsy) — a linha com metadata NULL some.
            assert "obs-null-meta" not in ids, (
                "Se isto falhar, o comportamento do SQLite mudou; revisar o teste"
            )
        finally:
            conn.close()


class TestDocumentIngestMetadataRegression:
    """Regressão do bug C1: em run_ingestion(), `doc_metadata` era usado no
    INSERT em document_memories antes de ser definido."""

    SCRIPT = PROJECT_ROOT / "scripts" / "document_ingest.py"

    def test_doc_metadata_defined_before_use(self):
        source = self.SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)

        run_ingestion = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run_ingestion":
                run_ingestion = node
                break
        assert run_ingestion is not None, "run_ingestion() não encontrada"

        first_store = None
        first_load = None
        for node in ast.walk(run_ingestion):
            if isinstance(node, ast.Name) and node.id == "doc_metadata":
                if isinstance(node.ctx, ast.Store):
                    if first_store is None or node.lineno < first_store:
                        first_store = node.lineno
                elif isinstance(node.ctx, ast.Load):
                    if first_load is None or node.lineno < first_load:
                        first_load = node.lineno

        assert first_load is not None, (
            "doc_metadata não é usado em run_ingestion(); o INSERT em "
            "document_memories deve serializá-lo via json.dumps(doc_metadata)"
        )
        assert first_store is not None, (
            "doc_metadata é usado mas nunca atribuído em run_ingestion() (bug C1)"
        )
        assert first_store < first_load, (
            f"doc_metadata usado (linha {first_load}) antes de ser definido "
            f"(linha {first_store}) — regressão do bug C1"
        )
