"""Revisão diária automática (review_writer) — Memória Viva."""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts.knowledge import review_writer as rw

NOW = datetime(2026, 6, 19, 8, 0, 0)


def _conn(rows):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE dream_cycle_log (id INTEGER PRIMARY KEY, started_at TEXT, "
              "duration_s REAL, observations_processed INT, ended_reason TEXT)")
    c.executemany("INSERT INTO dream_cycle_log (started_at,duration_s,observations_processed,ended_reason)"
                  " VALUES (?,?,?,?)", rows)
    c.commit()
    return c


def test_verdict_ok_quando_ciclo_de_hoje_ok():
    cycles = [{"started_at": "2026-06-19T03:00:00", "ended_reason": "ok"}]
    status, flags = rw._verdict(cycles, now=NOW)
    assert status == "✅" and flags == []


def test_verdict_alerta_quando_error():
    cycles = [{"started_at": "2026-06-19T03:00:00", "ended_reason": "error"}]
    status, flags = rw._verdict(cycles, now=NOW)
    assert status == "⚠️" and any("error" in f for f in flags)


def test_verdict_alerta_sem_ciclo_hoje():
    cycles = [{"started_at": "2026-06-17T03:00:00", "ended_reason": "ok"}]
    _, flags = rw._verdict(cycles, now=NOW)
    assert any("Sem ciclo do dream hoje" in f for f in flags)


def test_render_inclui_secoes(tmp_path):
    health = {"path": "2026-06-19.md", "alerts": ["M2: só 1/7"]}
    md = rw.render_review([{"started_at": "2026-06-19T03:00:00", "duration_s": 50.0,
                            "observations_processed": 30, "ended_reason": "ok"}],
                          health, ["ComfyUI", "michel"], now=NOW)
    assert "type: daily-review" in md
    assert "## Ciclos do dream (M9)" in md and "## Segregação por projeto" in md
    assert "ComfyUI, michel" in md and "M2: só 1/7" in md


def test_run_escreve_arquivo(tmp_path, monkeypatch):
    conn = _conn([("2026-06-19T03:00:00", 50.0, 30, "ok")])
    # run() lê os ciclos e então fecha a conexão — fechar de verdade é ok aqui.
    monkeypatch.setattr("core.database.get_connection", lambda: conn)
    saude = tmp_path / "saude"
    temporal = tmp_path / "temporal"
    (temporal / "ComfyUI").mkdir(parents=True)
    rw.run(saude_root=saude, temporal_root=temporal, now=NOW)
    out = saude / "revisao-2026-06-19.md"
    assert out.exists() and "ComfyUI" in out.read_text()
