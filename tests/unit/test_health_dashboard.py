"""F3.3 health_dashboard — M1-M9 → snapshot na Ínsula (doc 08 §11).

DB in-memory real + vault temporário (R1/R5). Garante: métricas computáveis batem,
não-mensuráveis viram n/a (não inventa), alertas aplicam thresholds §9.3, e o snapshot
é idempotente (sobrescreve o do dia).
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts import health_dashboard as hd

NOW = datetime(2026, 6, 18, 12, 0, 0)

_DDL = """
CREATE TABLE observations (id TEXT PRIMARY KEY, archived INTEGER DEFAULT 0, metadata JSON);
CREATE TABLE neurons (id TEXT PRIMARY KEY, label TEXT, type TEXT, created_at TIMESTAMP, updated_at TIMESTAMP);
"""


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(_DDL)
    from core.database import ensure_migrations
    ensure_migrations(c)   # cria dream_cycle_log
    return c


def _write(path: Path, *, ntype: str, last_updated: str, **extra) -> None:
    fm = {"type": ntype, "last_updated": last_updated, **extra}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False)
                    + "---\n# T\n\nx\n", encoding="utf-8")


@pytest.fixture()
def vault(tmp_path):
    t = tmp_path / "temporal"
    p = t / "Hive-Mind" / "atlas"
    _write(p / "neuronio-a.md", ntype="fact", last_updated="2026-06-10 10:00", aliases=["x"])
    _write(p / "neuronio-b.md", ntype="decision", last_updated="2025-01-01 10:00")  # stale
    (p / "neuronio-b.md").write_text((p / "neuronio-b.md").read_text() + "\nrelated: [[x]]\n")
    return t


def test_m9_na_sem_ciclo(vault):
    c = _conn()
    m = hd.m9_dream_survival(c)
    assert m["value"] == hd.NA and m["cycles_7d"] == 0
    c.close()


def test_m9_ok_quando_dentro_do_orcamento(vault):
    c = _conn()
    c.execute("INSERT INTO dream_cycle_log (started_at, duration_s, ended_reason) VALUES (datetime('now'), 120.0, 'ok')")
    c.commit()
    m = hd.m9_dream_survival(c, max_cycle_s=600)
    assert m["ok"] is True and m["value"] == 120.0
    c.close()


def test_m9_alerta_quando_estoura(vault):
    c = _conn()
    c.execute("INSERT INTO dream_cycle_log (started_at, duration_s, ended_reason) VALUES (datetime('now'), 999.0, 'BUDGET_EXHAUSTED')")
    c.commit()
    m = hd.m9_dream_survival(c, max_cycle_s=600)
    assert m["ok"] is False
    c.close()


def test_compute_metrics_e_na(vault):
    c = _conn()
    m = hd.compute_metrics(c, temporal_root=vault, daily_root=vault / "nope",
                           weekly_root=vault / "nope", sessions_root=vault / "nope", now=NOW)
    assert m["M5_topic_consolidation"] == hd.NA      # não-mensurável → n/a (não inventa)
    assert m["M8_decision_staleness_pct"] == 100.0   # 1/1 decision é stale
    assert isinstance(m["M4_orphan_pct"], float)     # neuronio-a sem related → órfão
    c.close()


def test_alerts_aplicam_thresholds(vault):
    c = _conn()
    m = hd.compute_metrics(c, temporal_root=vault, daily_root=vault / "nope",
                           weekly_root=vault / "nope", sessions_root=vault / "nope", now=NOW)
    alerts = hd.evaluate_alerts(m)
    assert any("M2" in a for a in alerts)   # 0 daily logs < 5
    assert any("M8" in a for a in alerts)   # 100% stale > 30%


def test_snapshot_idempotente(vault, tmp_path):
    c = _conn()
    m = hd.compute_metrics(c, temporal_root=vault, daily_root=vault / "nope",
                           weekly_root=vault / "nope", sessions_root=vault / "nope", now=NOW)
    saude = tmp_path / "saude"
    p1 = hd.write_snapshot(m, [], saude_root=saude, now=NOW)
    p2 = hd.write_snapshot(m, [], saude_root=saude, now=NOW)
    assert p1 == p2 and p1.name == "2026-06-18.md"
    assert len(list(saude.glob("*.md"))) == 1   # sobrescreve, não duplica
    c.close()
