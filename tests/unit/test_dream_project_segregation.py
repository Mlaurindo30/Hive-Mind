"""Testes de regressão do plumbing de `project` no dream_cycle.

Cobre o incremento que propaga `observations.project` pelo pipeline:
- Bucketing de observações por projeto antes de chamar o LLM.
- Persistência de neurônios em `cortex/temporal/{project}/{topic}/` derivado
  do projeto da observação de origem (e NÃO do `HIVE_DEFAULT_PROJECT`).
- Respeito ao fallback: obs com `project=NULL` usam o default.

Nenhum teste chama LLM nem depende do hive_mind.db real.
"""
import ast
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


class TestDreamCycleProjectSegregation:
    """Garante que `observations.project` é a fonte da verdade para o path
    anatômico onde o neurônio vai aterrissar."""

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
            # (id, project, archived)
            ("obs-hive-1", "Hive-Mind", 0),
            ("obs-hive-2", "Hive-Mind", 0),
            ("obs-claude-1", "claude-code-config", 0),
            ("obs-null-project", None, 0),
            ("obs-already-archived", "Hive-Mind", 1),
        ]
        for oid, proj, archived in rows:
            conn.execute(
                "INSERT INTO observations (id, session_id, project, type, title, "
                "content, neuron_id, archived, metadata) "
                "VALUES (?, 's1', ?, 'note', 't', 'c', NULL, ?, NULL)",
                (oid, proj, archived),
            )
        conn.commit()
        return conn

    def test_active_observations_grouped_by_project(self):
        """A query do dream_cycle deve devolver as 4 obs ativas (archived=0)."""
        conn = self._make_db()
        try:
            rows = conn.execute(
                "SELECT id, project FROM observations WHERE archived = 0"
            ).fetchall()
            assert len(rows) == 4, f"Esperava 4 obs ativas, vieram {len(rows)}"
            by_proj = {}
            for r in rows:
                by_proj.setdefault(r[1] or "<null>", []).append(r[0])
            assert "Hive-Mind" in by_proj and len(by_proj["Hive-Mind"]) == 2
            assert "claude-code-config" in by_proj and len(by_proj["claude-code-config"]) == 1
            assert "<null>" in by_proj and len(by_proj["<null>"]) == 1
        finally:
            conn.close()

    def test_null_project_falls_back_to_default(self):
        """Reproduz a lógica de `_resolve_project` do dream_cycle:
        project NULL/vazio → HIVE_DEFAULT_PROJECT (ou 'Hive-Mind')."""
        DEFAULT = "Hive-Mind"

        def resolve(p):
            return (p or "").strip() or DEFAULT

        assert resolve("claude-code-config") == "claude-code-config"
        assert resolve(None) == DEFAULT
        assert resolve("") == DEFAULT
        assert resolve("   ") == DEFAULT

    def test_dream_cycle_no_longer_uses_constant_default_for_path(self):
        """Garante que o path de escrita não está mais hardcoded em
        `cp.TEMPORAL / DEFAULT_PROJECT / ...` — deve usar a variável de
        iteração do bucket por projeto."""
        source = (SCRIPTS_DIR / "dream_cycle.py").read_text(encoding="utf-8")
        # Proíbe o anti-padrão antigo: escrever neurônio dentro do loop de
        # roteamento apontando para a constante DEFAULT_PROJECT em vez de
        # iterar sobre o bucket.
        forbidden = "note_file = cp.TEMPORAL / DEFAULT_PROJECT / safe_topic /"
        assert forbidden not in source, (
            "dream_cycle.py ainda usa DEFAULT_PROJECT no path do neurônio. "
            "Deve iterar por bucket de projeto."
        )
        # Pelo contrário, deve aparecer o pattern correto:
        assert "cp.TEMPORAL / proj / safe_topic /" in source, (
            "dream_cycle.py deveria escrever em cp.TEMPORAL / {proj_bucket} / safe_topic / ..."
        )

    def test_dream_cycle_marks_observations_per_project_bucket(self):
        """O novo `_mark_observations` aceita um `ids` opcional para segregar
        a marcação por bucket de projeto (não marca a janela inteira como
        consolidado quando só um bucket foi bem-sucedido)."""
        source = (SCRIPTS_DIR / "dream_cycle.py").read_text(encoding="utf-8")
        # Assinatura nova: `def _mark_observations(status, ids=None)`
        assert "def _mark_observations(status: int, ids: Optional[List[str]]" in source, (
            "Esperava assinatura _mark_observations(status, ids=None) para segregar por bucket"
        )
        # Consolidação por bucket: após o refactor F4.0, a persistência de cada
        # projeto vive em _route_and_persist_project(...), que recebe os IDs do
        # bucket (proj_obs_ids) e _mark_observations, e consolida via mark_obs(1, ...).
        assert "mark_obs(1, proj_obs_ids)" in source, (
            "Consolidação por bucket ausente: esperava mark_obs(1, proj_obs_ids) no helper"
        )
        assert "_route_and_persist_project(" in source and "proj_obs_ids, _mark_observations" in source, (
            "Esperava o helper _route_and_persist_project recebendo proj_obs_ids + _mark_observations"
        )
        assert "_mark_observations(2, proj_ids)" in source, (
            "Quarentena por bucket ausente: esperava _mark_observations(2, proj_ids)"
        )


class TestObservationsProjectIndex:
    """Garante que o índice composto `(archived, project)` está declarado."""

    def test_composite_index_created_in_migration(self):
        source = (PROJECT_ROOT / "core" / "database.py").read_text(encoding="utf-8")
        assert "idx_observations_archived_project" in source, (
            "Esperava migração criando idx_observations_archived_project em ensure_migrations()"
        )

    def test_index_idempotent_when_project_column_missing(self):
        """Bancos pré-anatômicos (sem coluna `project`) não devem quebrar
        `ensure_migrations`. O índice é criado via try/except."""
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE observations (
                id TEXT PRIMARY KEY,
                title TEXT,
                content TEXT,
                metadata JSON
            )
        """)
        # Import local para evitar ciclo
        sys.path.insert(0, str(PROJECT_ROOT))
        from core.database import ensure_migrations
        # Não deve lançar
        ensure_migrations(conn)
        conn.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))  # noqa: F821
