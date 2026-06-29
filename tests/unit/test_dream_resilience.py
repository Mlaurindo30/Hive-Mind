"""F4.0 — resiliência do dream multi-projeto (doc 08 §11/Fase 4).

Garante a classificação de M9 no wrapper run_dream_cycle:
- erro num projeto não aborta → ended_reason='partial' (ciclo sobreviveu);
- exceção no inner → 'error' (e re-levanta);
- sem erros + persistiu → 'ok'; vazio → 'empty'.
E que _route_and_persist_project propaga exceção (p/ o chamador isolar).
"""
import sys
import sqlite3
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.dream import dream_cycle as dc


@pytest.fixture()
def capture_m9(monkeypatch):
    """Captura o que run_dream_cycle gravaria em dream_cycle_log (sem tocar no DB)."""
    seen = {}
    monkeypatch.setattr(dc, "_log_dream_cycle",
                        lambda started, t0, obs, reason: seen.update(obs=obs, reason=reason))
    return seen


def test_partial_quando_um_projeto_falha(capture_m9, monkeypatch):
    monkeypatch.setattr(dc, "_run_dream_cycle_inner",
                        lambda: {"observations": 30, "persisted": 5, "errors": 2})
    dc.run_dream_cycle()
    assert capture_m9["reason"] == "partial"   # sobreviveu apesar de 2 projetos falharem
    assert capture_m9["obs"] == 30


def test_ok_quando_sem_erros(capture_m9, monkeypatch):
    monkeypatch.setattr(dc, "_run_dream_cycle_inner",
                        lambda: {"observations": 30, "persisted": 5, "errors": 0})
    dc.run_dream_cycle()
    assert capture_m9["reason"] == "ok"


def test_empty_quando_sem_obs(capture_m9, monkeypatch):
    monkeypatch.setattr(dc, "_run_dream_cycle_inner",
                        lambda: {"observations": 0, "persisted": 0, "errors": 0})
    dc.run_dream_cycle()
    assert capture_m9["reason"] == "empty"


def test_error_quando_inner_levanta(capture_m9, monkeypatch):
    def boom():
        raise RuntimeError("database is locked")
    monkeypatch.setattr(dc, "_run_dream_cycle_inner", boom)
    with pytest.raises(RuntimeError):
        dc.run_dream_cycle()
    assert capture_m9["reason"] == "error"   # registra antes de re-levantar


def test_route_and_persist_propaga_excecao():
    """O helper NÃO engole erro — o chamador (loop) é quem isola por projeto."""
    class _Boom:
        @property
        def facts(self):
            raise RuntimeError("falha no roteador")
    with pytest.raises(RuntimeError):
        dc._route_and_persist_project(conn=None, now=None, proj="X",
                                      distilled=_Boom(), proj_obs_ids=["a"],
                                      mark_obs=lambda *a: None)


def test_main_help_nao_executa_ciclo(monkeypatch, capsys):
    monkeypatch.setattr(dc, "run_dream_cycle", lambda: (_ for _ in ()).throw(AssertionError("executou")))
    with pytest.raises(SystemExit) as exc:
        dc.main(["--help"])
    assert exc.value.code == 0
    assert "--once" in capsys.readouterr().out


def test_main_once_real_executa_uma_vez(monkeypatch):
    calls = []
    monkeypatch.setattr(dc, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(dc, "LLM_MODEL", "qwen2.5:3b")
    monkeypatch.setattr(dc, "run_dream_cycle", lambda: calls.append("run") or {"observations": 0})
    assert dc.main(["--once", "--real"]) == 0
    assert calls == ["run"]


def test_dream_k3_intake_grava_candidatos_sem_arquivar_observations():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE observations (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            project TEXT,
            type TEXT,
            title TEXT,
            content TEXT,
            created_at TEXT,
            neuron_id TEXT,
            archived INTEGER DEFAULT 0,
            metadata TEXT,
            workspace_id TEXT DEFAULT 'default'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO observations(id, project, type, title, content, created_at, archived, metadata, workspace_id)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            "obs-k3",
            "Hive-Mind",
            "discovery",
            "Discovery K3",
            '{"facts":["K3 cria candidatos"], "decisions":["Manter raw intacto"]}',
            "2026-06-28T00:00:00",
            '{"workspace_id":"team-k3"}',
            "team-k3",
        ),
    )
    rows = conn.execute("SELECT * FROM observations").fetchall()

    report = dc._run_k3_candidate_intake(conn, rows)

    assert report["candidates"] == 2
    assert conn.execute("SELECT archived FROM observations WHERE id='obs-k3'").fetchone()[0] == 0
    stored = conn.execute("SELECT knowledge_type, workspace_id FROM knowledge_candidates").fetchall()
    assert {(row[0], row[1]) for row in stored} == {("fact", "team-k3"), ("decision", "team-k3")}


def test_graph_push_respeita_limite_e_registra_backlog(monkeypatch, tmp_path):
    pushed_graphiti = []
    pushed_lightrag = []

    monkeypatch.setenv("HIVE_DREAM_GRAPH_PUSH_MAX", "1")
    monkeypatch.setenv("HIVE_DREAM_GRAPH_PUSH_BACKLOG", str(tmp_path / "graph-backlog.jsonl"))
    monkeypatch.setitem(
        sys.modules,
        "integrations.graphiti",
        types.SimpleNamespace(
            push_neuron=lambda nid, content, source="dream": pushed_graphiti.append((nid, content, source)) or True
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "core.lightrag_index",
        types.SimpleNamespace(
            index_memory_sync=lambda content, metadata=None: pushed_lightrag.append((content, metadata)) or None
        ),
    )

    report = dc._push_neurons_to_graphs([
        ("n1", "conteudo 1"),
        ("n2", "conteudo 2"),
        ("n3", "conteudo 3"),
    ])

    assert report == {"seen": 3, "pushed": 1, "deferred": 2}
    assert [item[0] for item in pushed_graphiti] == ["n1"]
    assert [item[1]["neuron_id"] for item in pushed_lightrag] == ["n1"]
    backlog = (tmp_path / "graph-backlog.jsonl").read_text(encoding="utf-8")
    assert '"neuron_id": "n2"' in backlog
    assert '"neuron_id": "n3"' in backlog
