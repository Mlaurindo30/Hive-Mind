#!/usr/bin/env python3
"""
scripts/review_writer.py — Revisão diária automática (Memória Viva).

Escreve um resumo do estado do cérebro em cortex/insula/saude/revisao-{data}.md:
último(s) ciclo(s) do dream (M9), saúde (alertas do snapshot do dia), segregação por
projeto e flags de atenção. Roda via systemd (sinapse-review.timer) — NÃO depende de
sessão de chat. File+DB. Escreve por default; --dry-run só imprime.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from core.paths import SAUDE_ROOT, TEMPORAL  # noqa: E402

_BAD = {"error", "BUDGET_EXHAUSTED"}


def recent_cycles(conn, *, limit: int = 6) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT started_at, duration_s, observations_processed, ended_reason "
            "FROM dream_cycle_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def project_folders(temporal_root: Path = TEMPORAL) -> list[str]:
    if not temporal_root.exists():
        return []
    skip = {"arquivo", "hipocampo", "_global"}
    return sorted(d.name for d in temporal_root.iterdir()
                  if d.is_dir() and not d.name.startswith("_") and d.name not in skip)


def latest_health(saude_root: Path = SAUDE_ROOT, *, now: Optional[datetime] = None) -> Optional[dict]:
    if not saude_root.exists():
        return None
    snaps = sorted(saude_root.glob("20*-*-*.md"))
    if not snaps:
        return None
    txt = snaps[-1].read_text(errors="ignore")
    alerts = [l.strip("- ").strip() for l in txt.splitlines() if "⚠️" in l]
    return {"path": snaps[-1].name, "alerts": alerts}


def _verdict(cycles: list[dict], *, now: datetime) -> tuple[str, list[str]]:
    """(emoji_status, flags). Olha o ciclo mais recente do dia."""
    flags: list[str] = []
    if not cycles:
        return "❓", ["Nenhum ciclo do dream registrado (timer rodou?)."]
    last = cycles[0]
    today = now.strftime("%Y-%m-%d")
    ran_today = str(last.get("started_at", "")).startswith(today)
    if not ran_today:
        flags.append(f"Sem ciclo do dream hoje ({today}); último: {last.get('started_at')}.")
    if last.get("ended_reason") in _BAD:
        flags.append(f"Último ciclo terminou em '{last['ended_reason']}' — investigar.")
    status = "✅" if last.get("ended_reason") in ("ok", "partial") and ran_today else "⚠️"
    return status, flags


def render_review(cycles: list[dict], health: Optional[dict], projects: list[str], *,
                  now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    status, flags = _verdict(cycles, now=now)
    rows = "\n".join(
        f"| {c.get('started_at','?')} | {c.get('duration_s','?')} | "
        f"{c.get('observations_processed','?')} | {c.get('ended_reason','?')} |"
        for c in cycles) or "| _(sem registros)_ | | | |"
    h_line = (f"Snapshot `{health['path']}` · {len(health['alerts'])} alerta(s)"
              if health else "_(sem snapshot de saúde)_")
    h_alerts = "\n".join(f"- ⚠️ {a}" for a in (health or {}).get("alerts", [])) or "- ✅ sem alertas"
    flag_block = "\n".join(f"- ⚠️ {f}" for f in flags) or "- ✅ nada a reportar"
    return f"""---
type: daily-review
date: {now.strftime('%Y-%m-%d')}
status: {status}
---
# Revisão Diária — {now.strftime('%Y-%m-%d')} {status}

<!-- auto:gerado por review_writer.py (sinapse-review.timer) -->

## Ciclos do dream (M9)
| started_at | duração (s) | obs | desfecho |
|---|---|---|---|
{rows}

## Saúde
{h_line}
{h_alerts}

## Segregação por projeto
{len(projects)} projeto(s) em `cortex/temporal/`: {', '.join(projects) or '_(nenhum)_'}

## Atenção
{flag_block}
"""


def write_review(content: str, saude_root: Path = SAUDE_ROOT, *,
                 now: Optional[datetime] = None) -> Path:
    now = now or datetime.now()
    saude_root.mkdir(parents=True, exist_ok=True)
    dest = saude_root / f"revisao-{now.strftime('%Y-%m-%d')}.md"
    dest.write_text(content, encoding="utf-8")
    return dest


def run(*, saude_root: Path = SAUDE_ROOT, temporal_root: Path = TEMPORAL,
        dry_run: bool = False, now: Optional[datetime] = None) -> str:
    from core.database import get_connection
    now = now or datetime.now()
    conn = get_connection()
    try:
        cycles = recent_cycles(conn)
    finally:
        conn.close()
    content = render_review(cycles, latest_health(saude_root, now=now),
                            project_folders(temporal_root), now=now)
    if dry_run:
        print(content)
    else:
        dest = write_review(content, saude_root, now=now)
        print(f"[review] escrito em {dest}")
    return content


def main() -> int:
    ap = argparse.ArgumentParser(description="Revisão diária do cérebro (insula/saude).")
    ap.add_argument("--dry-run", action="store_true", help="imprime, não escreve")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
