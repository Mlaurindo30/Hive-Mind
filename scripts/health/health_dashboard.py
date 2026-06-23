#!/usr/bin/env python3
"""
scripts/health_dashboard.py — Painel de saúde da memória (Memória Viva F3.3/F4.6).

Calcula M1-M12 (§9.2/§9.3) e grava um snapshot idempotente em
cortex/insula/saude/YYYY-MM-DD.md com seção de alertas.

HONESTIDADE DE SCHEMA (R1/R2 do §14): a §9.2 original citava colunas/tabelas que NÃO
existem (backlinks_count, last_reviewed_at, merge_log). Aqui cada métrica é calculada
do que é REALMENTE mensurável (DB neurons + arquivos do vault + dream_cycle_log). O que
ainda não dá pra medir vira `n/a` — nunca inventamos número. Sem LLM, sem load_env (R3).

  M1  atoms_created_per_day      neurons criados nas últimas 24h (DB)
  M2  daily_logs_last_7d         arquivos em cerebelo/diario c/ data nos últimos 7d
  M3  session_logs_last_30d      arquivos em cerebelo/sessoes mtime < 30d
  M4  orphan_neurons_pct         neuronio-*.md sem `related:` ÷ total
  M5  topic_consolidation        n/a (sem log de merge ainda)
  M6  aliases_coverage_pct       neuronio-*.md com `aliases:` ÷ total
  M7  weekly_summaries_12w       arquivos em cerebelo/semanal
  M8  decision_staleness_pct     decisions > 180d ÷ total decisions (frontmatter)
  M9  dream_survival             pior duração de ciclo nos últimos 7d vs MAX_CYCLE_SECONDS
  M10 decisions_promoted_30d     dec-*.md em frontal/decisoes criados nos últimos 30d
  M11 patterns_distilled_90d     *.md em cerebelo/padroes criados nos últimos 90d
  M12 conflicts_open             count do último conflict-report em insula/conflitos
  M13 alerts_dispatched_today    alerta-*.md (type: health-alert) em inbox/hoje
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from core import paths as cp  # noqa: E402
from core.database import get_connection, ensure_migrations  # noqa: E402
from scripts.knowledge.drift_detector import scan_neuronios, DECISION_TYPES  # noqa: E402
from scripts.health.alert_dispatcher import m13_alerts_dispatched_today  # noqa: E402

MAX_CYCLE_SECONDS = int(os.environ.get("HIVE_MAX_CYCLE_SECONDS", "600"))
NA = "n/a"


# ---- métricas individuais (puras, testáveis) -------------------------------
def m1_atoms_per_day(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM neurons WHERE created_at > datetime('now','-1 day')"
    ).fetchone()[0]


def _count_dated_md(root: Path, *, days: int, now: datetime) -> int:
    if not root.exists():
        return 0
    n = 0
    for f in root.rglob("*.md"):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            continue
        if 0 <= (now - d).days < days:
            n += 1
    return n


def m2_daily_last_7d(daily_root: Path, *, now: datetime) -> int:
    return _count_dated_md(daily_root, days=7, now=now)


def m3_sessions_last_30d(sessions_root: Path, *, now: datetime) -> int:
    if not sessions_root.exists():
        return 0
    cutoff = now.timestamp() - 30 * 86400
    return sum(1 for f in sessions_root.rglob("*.md") if f.stat().st_mtime >= cutoff)


def _neuronio_pct(temporal_root: Path, predicate) -> Optional[float]:
    files = [f for f in temporal_root.rglob("neuronio-*.md")
             if "arquivo" not in f.relative_to(temporal_root).parts[:1]] \
        if temporal_root.exists() else []
    if not files:
        return None
    hit = sum(1 for f in files if predicate(f.read_text(errors="ignore")))
    return round(hit * 100.0 / len(files), 1)


def m4_orphan_pct(temporal_root: Path) -> Optional[float]:
    """% de neurônios sem wikilink de saída.

    Critério real de "órfão" no vault: o neurônio não tem seção
    `## Sinapses` E não tem nenhum `[[wikilink]]` no corpo. O medidor
    antigo procurava apenas a string `related:` no frontmatter, que
    não é o padrão emitido pelo `_route_and_persist_project`
    (dream_cycle.py) — o padrão é a seção `## Sinapses` com
    `[[wikilinks]]`. Corrigido em 2026-06-23.
    """
    wikilink_re = re.compile(r"\[\[[^\]]+\]\]")
    def is_orphan(content: str) -> bool:
        return "## Sinapses" not in content and not wikilink_re.search(content)
    return _neuronio_pct(temporal_root, is_orphan)


def m6_aliases_coverage_pct(temporal_root: Path) -> Optional[float]:
    """% de neurônios com aliases REAIS (lista não-vazia).

    O medidor antigo verificava apenas a presença da chave
    `aliases:` no frontmatter, mas o dream_cycle.py sempre emite
    `aliases: []` (lista vazia) quando o fato não tem alias. O
    critério correto é aliases: [item, ...] com pelo menos 1 item.
    Corrigido em 2026-06-23.
    """
    aliases_re = re.compile(r"aliases:\s*\[\s*([^\]]*?)\s*\]")
    def has_real_aliases(content: str) -> bool:
        m = aliases_re.search(content)
        return bool(m and m.group(1).strip())
    return _neuronio_pct(temporal_root, has_real_aliases)


def m7_weekly_12w(weekly_root: Path) -> int:
    return len(list(weekly_root.rglob("*.md"))) if weekly_root.exists() else 0


def m7_weekly_threshold_breached(now: datetime, current_count: int,
                                 *, birth_date: Optional[datetime] = None,
                                 tolerance_weeks: int = 1) -> bool:
    """True se o nº de weeklies for menor que o esperado para o tempo
    de existência do vault.

    O threshold absoluto de "8 em 12 semanas" só faz sentido se o
    vault tiver 12+ semanas de história. Vaults jovens (< 8 semanas)
    devem ser avaliados proporcionalmente: aceita-se `weeks_existed -
    tolerance_weeks` weekly files como saudável.
    """
    if current_count is None:
        return False
    if birth_date is None:
        # Fallback: usa o mtime do diretório `weekly_root` se existir,
        # senão o primeiro weekly encontrado.
        weekly_root = Path(cp.WEEKLY_ROOT)
        if weekly_root.exists():
            try:
                files = sorted(weekly_root.rglob("*.md"))
                if files:
                    birth_date = datetime.fromtimestamp(files[0].stat().st_mtime)
            except OSError:
                pass
    if birth_date is None:
        # Sem referência: comportamento legado (alerta em <8).
        return current_count < 8
    weeks_existed = max(1, (now - birth_date).days // 7)
    expected = max(1, weeks_existed - tolerance_weeks)
    return current_count < expected


def m8_decision_staleness_pct(temporal_root: Path, *, days: int = 180,
                              now: Optional[datetime] = None) -> Optional[float]:
    decisions = [n for n in scan_neuronios(temporal_root, now=now)
                 if n["type"] in DECISION_TYPES and n["age_days"] is not None]
    if not decisions:
        return None
    stale = sum(1 for n in decisions if n["age_days"] > days)
    return round(stale * 100.0 / len(decisions), 1)


def m9_dream_survival(conn, *, max_cycle_s: int = MAX_CYCLE_SECONDS) -> dict:
    """Pior duração e desfecho nos últimos 7d. {'value': n/a} se não houve ciclo."""
    row = conn.execute(
        """SELECT MAX(duration_s) AS worst, COUNT(*) AS n,
                  SUM(CASE WHEN ended_reason IN ('error','BUDGET_EXHAUSTED') THEN 1 ELSE 0 END) AS bad
           FROM dream_cycle_log WHERE started_at > datetime('now','-7 days')"""
    ).fetchone()
    if not row or row["n"] == 0:
        return {"value": NA, "ok": None, "cycles_7d": 0}
    worst = row["worst"] or 0.0
    ok = worst <= max_cycle_s and (row["bad"] or 0) == 0
    return {"value": round(worst, 1), "ok": ok, "cycles_7d": row["n"]}


# ---- F4.6 — métricas do lobo frontal + padrões + conflitos ----------------
def m10_decisions_promoted_30d(decisions_root: Path = cp.DECISIONS_ROOT, *,
                               now: Optional[datetime] = None) -> int:
    if not decisions_root.exists():
        return 0
    now = now or datetime.now()
    cutoff = now.timestamp() - 30 * 86400
    return sum(1 for f in decisions_root.rglob("dec-*.md")
               if f.stat().st_mtime >= cutoff)


def m11_patterns_distilled_90d(padroes_root: Path = cp.PADROES_ROOT, *,
                                now: Optional[datetime] = None) -> int:
    if not padroes_root.exists():
        return 0
    now = now or datetime.now()
    cutoff = now.timestamp() - 90 * 86400
    return sum(1 for f in padroes_root.glob("*.md") if f.stat().st_mtime >= cutoff)


def m12_conflicts_open(conflicts_root: Path = cp.CONFLICTS_ROOT) -> int:
    """Lê o count do último conflict-report. 0 se não há relatório."""
    if not conflicts_root.exists():
        return 0
    reports = sorted(conflicts_root.glob("*.md"))
    if not reports:
        return 0
    content = reports[-1].read_text(errors="ignore")
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return 0
    try:
        fm = yaml.safe_load(m.group(1))
        return int(fm.get("count", 0))
    except Exception:
        return 0


# ---- orquestração ----------------------------------------------------------
def compute_metrics(conn, *, temporal_root: Path = cp.TEMPORAL,
                    daily_root: Path = cp.DAILY_ROOT, weekly_root: Path = cp.WEEKLY_ROOT,
                    sessions_root: Path = cp.SESSIONS_ROOT,
                    decisions_root: Path = cp.DECISIONS_ROOT,
                    padroes_root: Path = cp.PADROES_ROOT,
                    conflicts_root: Path = cp.CONFLICTS_ROOT,
                    inbox_root: Path = cp.INBOX_ROOT,
                    now: Optional[datetime] = None,
                    max_cycle_s: int = MAX_CYCLE_SECONDS) -> dict:
    now = now or datetime.now()
    return {
        "M1_atoms_per_day": m1_atoms_per_day(conn),
        "M2_daily_logs_7d": m2_daily_last_7d(daily_root, now=now),
        "M3_session_logs_30d": m3_sessions_last_30d(sessions_root, now=now),
        "M4_orphan_pct": m4_orphan_pct(temporal_root),
        "M5_topic_consolidation": NA,
        "M6_aliases_coverage_pct": m6_aliases_coverage_pct(temporal_root),
        "M7_weekly_12w": m7_weekly_12w(weekly_root),
        "M8_decision_staleness_pct": m8_decision_staleness_pct(temporal_root, now=now),
        "M9_dream_survival": m9_dream_survival(conn, max_cycle_s=max_cycle_s),
        "M10_decisions_promoted_30d": m10_decisions_promoted_30d(decisions_root, now=now),
        "M11_patterns_distilled_90d": m11_patterns_distilled_90d(padroes_root, now=now),
        "M12_conflicts_open": m12_conflicts_open(conflicts_root),
        "M13_alerts_dispatched_today": m13_alerts_dispatched_today(inbox_root, now=now),
    }


def evaluate_alerts(m: dict, *, now: Optional[datetime] = None) -> list[str]:
    """Aplica os thresholds §9.3 onde a métrica é computável (None/n/a = ignora)."""
    alerts = []
    if m["M2_daily_logs_7d"] < 5:
        alerts.append(f"M2: só {m['M2_daily_logs_7d']}/7 daily logs (< 5).")
    if isinstance(m["M4_orphan_pct"], (int, float)) and m["M4_orphan_pct"] > 15:
        alerts.append(f"M4: órfãos em {m['M4_orphan_pct']}% (> 15%).")
    if m7_weekly_threshold_breached(now, m["M7_weekly_12w"]):
        alerts.append(f"M7: {m['M7_weekly_12w']} weekly(s) (abaixo do esperado p/ idade do vault).")
    if isinstance(m["M8_decision_staleness_pct"], (int, float)) and m["M8_decision_staleness_pct"] > 30:
        alerts.append(f"M8: decisões stale em {m['M8_decision_staleness_pct']}% (> 30%).")
    m9 = m["M9_dream_survival"]
    if m9.get("ok") is False:
        alerts.append(f"M9: dream cycle excedeu orçamento/erro (pior={m9['value']}s).")
    if isinstance(m.get("M10_decisions_promoted_30d"), int) and m["M10_decisions_promoted_30d"] == 0:
        alerts.append("M10: nenhuma decisão promovida nos últimos 30d.")
    if isinstance(m.get("M11_patterns_distilled_90d"), int) and m["M11_patterns_distilled_90d"] == 0:
        alerts.append("M11: nenhum padrão destilado nos últimos 90d.")
    if isinstance(m.get("M12_conflicts_open"), int) and m["M12_conflicts_open"] > 0:
        alerts.append(f"M12: {m['M12_conflicts_open']} conflito(s) aberto(s) aguardam revisão.")
    return alerts


def _fmt(v) -> str:
    return NA if v is None else str(v)


def render_snapshot(m: dict, alerts: list[str], *, now: datetime) -> str:
    m9 = m["M9_dream_survival"]
    m9_txt = NA if m9["value"] == NA else f"{m9['value']}s ({m9['cycles_7d']} ciclos/7d)"
    rows = [
        ("M1 átomos/dia", _fmt(m["M1_atoms_per_day"])),
        ("M2 daily logs (7d)", _fmt(m["M2_daily_logs_7d"])),
        ("M3 session logs (30d)", _fmt(m["M3_session_logs_30d"])),
        ("M4 órfãos %", _fmt(m["M4_orphan_pct"])),
        ("M5 topic consolidation", _fmt(m["M5_topic_consolidation"])),
        ("M6 aliases cobertura %", _fmt(m["M6_aliases_coverage_pct"])),
        ("M7 weeklies (12w)", _fmt(m["M7_weekly_12w"])),
        ("M8 decisões stale %", _fmt(m["M8_decision_staleness_pct"])),
        ("M9 dream survival", m9_txt),
        ("M10 decisões promovidas (30d)", _fmt(m.get("M10_decisions_promoted_30d"))),
        ("M11 padrões destilados (90d)", _fmt(m.get("M11_patterns_distilled_90d"))),
        ("M12 conflitos abertos", _fmt(m.get("M12_conflicts_open"))),
        ("M13 alertas despachados (hoje)", _fmt(m.get("M13_alerts_dispatched_today"))),
    ]
    table = "\n".join(f"| {k} | {v} |" for k, v in rows)
    alert_block = ("\n".join(f"- ⚠️ {a}" for a in alerts)
                   if alerts else "- ✅ Sem alertas.")
    return f"""---
type: health-snapshot
date: {now.strftime('%Y-%m-%d')}
---
# Saúde da Memória — {now.strftime('%Y-%m-%d')}

<!-- auto:gerado por health_dashboard.py — não editar à mão -->

## Métricas
| Métrica | Valor |
|---|---|
{table}

## Alertas
{alert_block}
"""


def write_snapshot(m: dict, alerts: list[str], *, saude_root: Path = cp.SAUDE_ROOT,
                   now: Optional[datetime] = None) -> Path:
    now = now or datetime.now()
    saude_root.mkdir(parents=True, exist_ok=True)
    dest = saude_root / f"{now.strftime('%Y-%m-%d')}.md"
    dest.write_text(render_snapshot(m, alerts, now=now), encoding="utf-8")
    return dest


# ---- F5.3 — Dashboard Dataview -----------------------------------------------

_DASHBOARD_TEMPLATE = """\
---
type: health-dashboard
description: Dashboard de saúde da memória (M1-M13) — gerado por health_dashboard.py
generated_at: {generated_at}
---
# Dashboard de Saúde da Memória

> Gerado em {generated_at} por `health_dashboard.py --generate-dashboard`.
> Requer plugin **Dataview** ativo no Obsidian para renderizar os blocos abaixo.

## Últimos 7 dias — métricas principais

```dataviewjs
const saude = '"cortex/insula/saude"';
const pages = dv.pages(saude)
  .filter(p => /^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(p.file.name))
  .sort(p => p.file.name, 'desc')
  .slice(0, 7);

function extractMetric(content, label) {{
  const re = new RegExp('\\\\| ' + label + ' \\\\| ([^|]+) \\\\|');
  const m = content.match(re);
  return m ? m[1].trim() : 'n/a';
}}

const rows = [];
for (const page of pages) {{
  const file = app.vault.getAbstractFileByPath(page.file.path);
  const content = await app.vault.read(file);
  rows.push([
    page.file.name,
    extractMetric(content, 'M1 átomos/dia'),
    extractMetric(content, 'M2 daily logs \\\\(7d\\\\)'),
    extractMetric(content, 'M4 órfãos %'),
    extractMetric(content, 'M9 dream survival'),
    extractMetric(content, 'M12 conflitos abertos'),
    extractMetric(content, 'M13 alertas despachados \\\\(hoje\\\\)'),
  ]);
}}

dv.table(
  ['Data', 'M1 átomos', 'M2 daily(7d)', 'M4 órfãos%', 'M9 dream', 'M12 conflitos', 'M13 alertas'],
  rows
);
```

## Histórico de alertas — últimos 30 dias

```dataviewjs
const saude = '"cortex/insula/saude"';
const pages = dv.pages(saude)
  .filter(p => /^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(p.file.name))
  .sort(p => p.file.name, 'desc')
  .slice(0, 30);

function extractAlerts(content) {{
  const m = content.match(/## Alertas\\n([\\s\\S]*?)(?=\\n## |$)/);
  if (!m) return [];
  return m[1].split('\\n')
    .filter(l => l.includes('⚠️'))
    .map(l => l.replace(/^-\\s*⚠️\\s*/, '').trim())
    .filter(Boolean);
}}

const alertRows = [];
for (const page of pages) {{
  const file = app.vault.getAbstractFileByPath(page.file.path);
  const content = await app.vault.read(file);
  for (const alert of extractAlerts(content)) {{
    alertRows.push([page.file.name, alert]);
  }}
}}

if (alertRows.length === 0) {{
  dv.paragraph('✅ Nenhum alerta nos últimos 30 dias.');
}} else {{
  dv.table(['Data', 'Alerta'], alertRows);
}}
```

## Tendência de M1 (átomos/dia) — últimos 30 dias

```dataviewjs
const saude = '"cortex/insula/saude"';
const pages = dv.pages(saude)
  .filter(p => /^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(p.file.name))
  .sort(p => p.file.name, 'asc')
  .slice(-30);

const rows = [];
for (const page of pages) {{
  const file = app.vault.getAbstractFileByPath(page.file.path);
  const content = await app.vault.read(file);
  const m = content.match(/\\| M1 átomos\\/dia \\| ([^|]+) \\|/);
  const v = m ? m[1].trim() : 'n/a';
  rows.push([page.file.name, v === 'n/a' ? v : Number(v)]);
}}

dv.table(['Data', 'M1 átomos/dia'], rows);
```
"""


def generate_dashboard(saude_root: Path = cp.SAUDE_ROOT) -> Path:
    """Gera `_Dashboard.md` com blocos Dataview JS em saude_root. Sobrescreve se existir."""
    saude_root.mkdir(parents=True, exist_ok=True)
    dest = saude_root / "_Dashboard.md"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    dest.write_text(
        _DASHBOARD_TEMPLATE.format(generated_at=generated_at),
        encoding="utf-8",
    )
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera snapshot de saúde da memória (M1-M13).")
    ap.add_argument("--dry-run", action="store_true", help="imprime, não escreve arquivo")
    ap.add_argument("--generate-dashboard", action="store_true",
                    help="Gera _Dashboard.md com blocos Dataview JS (F5.3)")
    args = ap.parse_args()

    if args.generate_dashboard:
        dest = generate_dashboard()
        print(f"[health] dashboard gerado em {dest}")
        return 0

    conn = get_connection()
    ensure_migrations(conn)
    now = datetime.now()
    try:
        m = compute_metrics(conn, now=now)
    finally:
        conn.close()
    alerts = evaluate_alerts(m, now=now)
    if args.dry_run:
        print(render_snapshot(m, alerts, now=datetime.now()))
    else:
        dest = write_snapshot(m, alerts)
        print(f"[health] snapshot escrito em {dest}")
        for a in alerts:
            print(f"  ⚠️ {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
