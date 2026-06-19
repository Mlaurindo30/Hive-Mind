"""F3.3 health_dashboard — M1-M9 → snapshot na Ínsula (doc 08 §11).

DB in-memory real + vault temporário (R1/R5). Garante: métricas computáveis batem,
não-mensuráveis viram n/a (não inventa), alertas aplicam thresholds §9.3, e o snapshot
é idempotente (sobrescreve o do dia).
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import os
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


# ---- F4.6 — M10/M11/M12 ---------------------------------------------------

def test_m10_zero_quando_sem_decisoes(tmp_path):
    assert hd.m10_decisions_promoted_30d(tmp_path / "nope", now=NOW) == 0


def test_m10_conta_dec_recentes(tmp_path):
    d = tmp_path / "decisions" / "Hive-Mind"
    d.mkdir(parents=True)
    (d / "dec-abc123.md").write_text("# x")
    (d / "dec-def456.md").write_text("# y")
    (d / "other.md").write_text("# ignored")   # não é dec-*.md
    assert hd.m10_decisions_promoted_30d(tmp_path / "decisions", now=NOW) == 2


def test_m10_ignora_arquivos_velhos(tmp_path):
    import time
    d = tmp_path / "decisions"
    d.mkdir()
    old = d / "dec-old.md"
    old.write_text("# old")
    # retrocede mtime em 91 dias
    ts = NOW.timestamp() - 91 * 86400
    os.utime(old, (ts, ts))
    assert hd.m10_decisions_promoted_30d(d, now=NOW) == 0


def test_m11_zero_quando_sem_padroes(tmp_path):
    assert hd.m11_patterns_distilled_90d(tmp_path / "nope", now=NOW) == 0


def test_m11_conta_padroes_recentes(tmp_path):
    p = tmp_path / "padroes"
    p.mkdir()
    (p / "padrao-a.md").write_text("# p")
    (p / "padrao-b.md").write_text("# q")
    assert hd.m11_patterns_distilled_90d(p, now=NOW) == 2


def test_m12_zero_quando_sem_relatorios(tmp_path):
    assert hd.m12_conflicts_open(tmp_path / "nope") == 0


def test_m12_le_count_do_ultimo_relatorio(tmp_path):
    c = tmp_path / "conflitos"
    c.mkdir()
    (c / "2026-06-18.md").write_text(
        "---\ntype: conflict-report\ndate: 2026-06-18\ncount: 3\n---\n# x\n"
    )
    assert hd.m12_conflicts_open(c) == 3


def test_m12_relatorio_sem_conflitos(tmp_path):
    c = tmp_path / "conflitos"
    c.mkdir()
    (c / "2026-06-18.md").write_text(
        "---\ntype: conflict-report\ndate: 2026-06-18\ncount: 0\n---\n# x\n"
    )
    assert hd.m12_conflicts_open(c) == 0


def test_compute_metrics_inclui_m10_m11_m12(tmp_path):
    c = _conn()
    m = hd.compute_metrics(
        c,
        temporal_root=tmp_path / "t",
        daily_root=tmp_path / "d",
        weekly_root=tmp_path / "w",
        sessions_root=tmp_path / "s",
        decisions_root=tmp_path / "dec",
        padroes_root=tmp_path / "pad",
        conflicts_root=tmp_path / "con",
        now=NOW,
    )
    assert "M10_decisions_promoted_30d" in m
    assert "M11_patterns_distilled_90d" in m
    assert "M12_conflicts_open" in m
    assert m["M10_decisions_promoted_30d"] == 0
    assert m["M11_patterns_distilled_90d"] == 0
    assert m["M12_conflicts_open"] == 0
    c.close()


def test_alerts_m10_m11_disparam_quando_zero(tmp_path):
    c = _conn()
    m = hd.compute_metrics(
        c,
        temporal_root=tmp_path / "t",
        daily_root=tmp_path / "d",
        weekly_root=tmp_path / "w",
        sessions_root=tmp_path / "s",
        decisions_root=tmp_path / "dec",
        padroes_root=tmp_path / "pad",
        conflicts_root=tmp_path / "con",
        now=NOW,
    )
    alerts = hd.evaluate_alerts(m)
    assert any("M10" in a for a in alerts)
    assert any("M11" in a for a in alerts)
    c.close()


def test_alert_m12_dispara_quando_ha_conflitos(tmp_path):
    con = tmp_path / "conflitos"
    con.mkdir()
    (con / "2026-06-18.md").write_text(
        "---\ntype: conflict-report\ndate: 2026-06-18\ncount: 2\n---\n"
    )
    c = _conn()
    m = hd.compute_metrics(
        c,
        temporal_root=tmp_path / "t",
        daily_root=tmp_path / "d",
        weekly_root=tmp_path / "w",
        sessions_root=tmp_path / "s",
        decisions_root=tmp_path / "dec",
        padroes_root=tmp_path / "pad",
        conflicts_root=con,
        now=NOW,
    )
    alerts = hd.evaluate_alerts(m)
    assert any("M12" in a and "2" in a for a in alerts)
    c.close()


def test_render_snapshot_contem_m10_m11_m12(tmp_path):
    c = _conn()
    m = hd.compute_metrics(
        c,
        temporal_root=tmp_path / "t",
        daily_root=tmp_path / "d",
        weekly_root=tmp_path / "w",
        sessions_root=tmp_path / "s",
        decisions_root=tmp_path / "dec",
        padroes_root=tmp_path / "pad",
        conflicts_root=tmp_path / "con",
        now=NOW,
    )
    snap = hd.render_snapshot(m, [], now=NOW)
    assert "M10" in snap
    assert "M11" in snap
    assert "M12" in snap
    c.close()
