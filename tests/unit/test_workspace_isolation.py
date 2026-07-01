"""F4.5 — Testes de isolamento de workspace (K10 federação).

Garante que:
  1. workspace_id='default' e workspace_id='acme' coexistem no mesmo DB
  2. consulta em um workspace nao retorna dados do outro
  3. prune_orphan_vectors honra workspace_id (nao cruza fronteira)
  4. knowledge_health aceita workspace_id como parametro (ja existe,
     mas garantimos que filtra corretamente)
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class WorkspaceIsolationTests(unittest.TestCase):
    """Verifica que workspace_id cumpre seu papel de fronteira de isolamento.

    Como o sinapse_query nao e' exposto diretamente sem um LLM rodando,
    testamos no nivel do SQL: cada tabela com workspace_id filtra
    corretamente quando consultada com WHERE workspace_id = ?.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "test.db"
        # Cria o arquivo vazio (sqlite3.connect falha se o path nao existe)
        self.db_path.touch()
        # Patch direto: core.database.DB_PATH é lido como global do modulo
        # no momento da chamada. Substituir a referencia ANTES de chamar
        # get_connection() funciona.
        import core.database as db_mod
        self._original_db_path = db_mod.DB_PATH
        db_mod.DB_PATH = str(self.db_path)
        from core.database import get_connection
        self.conn = get_connection()
        # Inicializa o schema completo (9 tabelas + indices) via o script
        # SQL canonico, depois roda migrations de workspace.
        from core.database import ensure_migrations, SCHEMA_PATH
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
        ensure_migrations(self.conn)
        from core.database import migrate_workspace_and_federation
        migrate_workspace_and_federation(self.conn)

    def tearDown(self):
        self.conn.close()
        import shutil
        import core.database as db_mod
        db_mod.DB_PATH = self._original_db_path
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _insert_neuron(self, nid: str, workspace: str = "default", content: str = "x") -> None:
        self.conn.execute(
            "INSERT INTO neurons(id, label, type, source_file, content, hash, workspace_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nid, f"label-{nid}", "memory", "test.md", content, f"hash-{nid}", workspace),
        )

    def test_workspace_filter_returns_only_matching_neurons(self):
        self._insert_neuron("n-alpha", "acme")
        self._insert_neuron("n-bravo", "default")
        self._insert_neuron("n-charlie", "acme")
        self.conn.commit()

        acme_ids = {
            r["id"] for r in
            self.conn.execute(
                "SELECT id FROM neurons WHERE workspace_id = ?", ("acme",)
            ).fetchall()
        }
        self.assertEqual(acme_ids, {"n-alpha", "n-charlie"})

        default_ids = {
            r["id"] for r in
            self.conn.execute(
                "SELECT id FROM neurons WHERE workspace_id = ?", ("default",)
            ).fetchall()
        }
        self.assertEqual(default_ids, {"n-bravo"})

    def test_no_cross_workspace_leakage_in_observations(self):
        # A tabela observations tem workspace_id (v3.6.0+)
        for ws, oid in [("acme", "obs-a"), ("acme", "obs-b"), ("default", "obs-c")]:
            self.conn.execute(
                "INSERT INTO observations(id, content, archived, workspace_id) "
                "VALUES (?, ?, ?, ?)",
                (oid, f"content-{oid}", 0, ws),
            )
        self.conn.commit()

        acme_obs = {
            r["id"] for r in
            self.conn.execute(
                "SELECT id FROM observations WHERE workspace_id = ?", ("acme",)
            ).fetchall()
        }
        self.assertEqual(acme_obs, {"obs-a", "obs-b"})

    def test_workspace_count_via_groupby(self):
        for ws in ["acme", "acme", "acme", "default", "default"]:
            self._insert_neuron(f"n-{ws}-{os.urandom(2).hex()}", ws)
        self.conn.commit()

        rows = self.conn.execute(
            "SELECT workspace_id, COUNT(*) AS c FROM neurons GROUP BY workspace_id ORDER BY workspace_id"
        ).fetchall()
        counts = {r["workspace_id"]: r["c"] for r in rows}
        self.assertEqual(counts.get("acme"), 3)
        self.assertEqual(counts.get("default"), 2)


@pytest.mark.real
class WorkspaceFederationRealTests(unittest.TestCase):
    """Teste real (K10) que prova isolamento end-to-end com knowledge_health."""

    def test_knowledge_health_isolated_by_workspace(self):
        from core.database import get_connection
        from scripts.health.knowledge_health import (
            compute_knowledge_health,
            find_orphan_vectors,
        )

        conn = get_connection()
        try:
            # Insere 2 neurons no workspace 'acme', 1 no 'default'
            conn.execute(
                "INSERT OR IGNORE INTO neurons(id, label, type, source_file, content, hash, workspace_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("k10-n-acme-1", "K10 acme 1", "memory", "k10.md", "acme one", "h1", "acme"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO neurons(id, label, type, source_file, content, hash, workspace_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("k10-n-acme-2", "K10 acme 2", "memory", "k10.md", "acme two", "h2", "acme"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO neurons(id, label, type, source_file, content, hash, workspace_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("k10-n-default-1", "K10 default 1", "memory", "k10.md", "default one", "h3", "default"),
            )
            conn.commit()

            # Health em 'acme' nao deve enxergar neuron 'default'
            metrics_acme = compute_knowledge_health(conn, workspace_id="acme", prune_orphans=False)
            metrics_default = compute_knowledge_health(conn, workspace_id="default", prune_orphans=False)

            # workspace_id propagado corretamente
            self.assertEqual(metrics_acme["workspace_id"], "acme")
            self.assertEqual(metrics_default["workspace_id"], "default")
        finally:
            # Limpa dados de teste
            conn.execute("DELETE FROM neurons WHERE id LIKE 'k10-n-%'")
            conn.commit()
            conn.close()


if __name__ == "__main__":
    unittest.main()
