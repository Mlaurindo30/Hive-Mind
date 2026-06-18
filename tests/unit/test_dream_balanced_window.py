"""Janela balanceada do dream (doc 08 §13.2.2 follow-up) — round-robin por projeto.

SQLite real in-memory (R1/R5). Garante que fetch_balanced_observations:
- abrange TODOS os projetos pendentes (não 1 por vez como o ORDER BY created_at);
- dentro de cada projeto pega a mais antiga primeiro;
- respeita o teto (LIMIT) — boundedness.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts import dream_cycle as dc


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE observations (id TEXT PRIMARY KEY, project TEXT, "
              "created_at TEXT, archived INTEGER DEFAULT 0)")
    return c


def _seed(c, rows):
    c.executemany("INSERT INTO observations (id, project, created_at, archived) "
                  "VALUES (?,?,?,?)", rows)
    c.commit()


def test_abrange_todos_os_projetos():
    """Hive-Mind tem MUITAS obs antigas; ComfyUI/Thoth poucas e recentes.
    A janela velha (created_at) pegaria só Hive-Mind; a balanceada pega os 3."""
    c = _conn()
    rows = [(f"hm{i}", "Hive-Mind", f"2026-01-{i:02d}", 0) for i in range(1, 21)]
    rows += [("cf1", "ComfyUI", "2026-06-01", 0), ("cf2", "ComfyUI", "2026-06-02", 0)]
    rows += [("th1", "Thoth", "2026-06-03", 0)]
    _seed(c, rows)
    obs = dc.fetch_balanced_observations(c, limit=6)
    projs = {o["project"] for o in obs}
    assert projs == {"Hive-Mind", "ComfyUI", "Thoth"}, projs
    c.close()


def test_round_robin_antiga_primeiro_por_projeto():
    """Os primeiros itens são a mais antiga de cada projeto (rank 1)."""
    c = _conn()
    _seed(c, [
        ("a1", "A", "2026-01-01", 0), ("a2", "A", "2026-02-01", 0),
        ("b1", "B", "2026-01-15", 0), ("b2", "B", "2026-02-15", 0),
    ])
    obs = dc.fetch_balanced_observations(c, limit=4)
    ids = [o["id"] for o in obs]
    # rank 1 de cada (a1, b1) antes do rank 2 (a2, b2)
    assert set(ids[:2]) == {"a1", "b1"}
    assert set(ids[2:]) == {"a2", "b2"}
    c.close()


def test_respeita_o_teto():
    c = _conn()
    _seed(c, [(f"x{i}", f"P{i%5}", f"2026-03-{i:02d}", 0) for i in range(1, 30)])
    assert len(dc.fetch_balanced_observations(c, limit=10)) == 10
    c.close()


def test_ignora_archived():
    c = _conn()
    _seed(c, [("p", "A", "2026-01-01", 0), ("q", "A", "2026-01-02", 1),
              ("r", "B", "2026-01-03", 2)])
    obs = dc.fetch_balanced_observations(c, limit=30)
    assert {o["id"] for o in obs} == {"p"}   # só archived=0
    c.close()


def test_obs_sem_projeto_vira_um_balde():
    """Obs com project NULL não somem — entram como '_sem_projeto'."""
    c = _conn()
    _seed(c, [("n1", None, "2026-01-01", 0), ("a1", "A", "2026-01-02", 0)])
    obs = dc.fetch_balanced_observations(c, limit=30)
    assert {o["id"] for o in obs} == {"n1", "a1"}
    c.close()
