"""F4.0 — resiliência do dream multi-projeto (doc 08 §11/Fase 4).

Garante a classificação de M9 no wrapper run_dream_cycle:
- erro num projeto não aborta → ended_reason='partial' (ciclo sobreviveu);
- exceção no inner → 'error' (e re-levanta);
- sem erros + persistiu → 'ok'; vazio → 'empty'.
E que _route_and_persist_project propaga exceção (p/ o chamador isolar).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts import dream_cycle as dc


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
