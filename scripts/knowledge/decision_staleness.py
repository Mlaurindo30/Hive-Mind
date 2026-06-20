#!/usr/bin/env python3
"""
scripts/decision_staleness.py — Relatório de decisões estagnadas (Memória Viva F3.2).

READ-ONLY: lista decisões (type=decision no frontmatter) sem revisão há > N dias (180)
para embutir no weekly (§5.6) e na Ínsula (saúde). NUNCA escreve em arquivos nem no DB.

Reaproveita drift_detector.scan_neuronios (mesma fonte da verdade: frontmatter +
last_updated). Sem LLM, sem load_env (R3).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from core.paths import TEMPORAL  # noqa: E402
from scripts.knowledge.drift_detector import scan_neuronios, DECISION_TYPES  # noqa: E402

DEFAULT_DAYS_STALE = 180


def _title(item: dict) -> str:
    """Título da decisão: 1ª H1 do corpo → alias → nome do arquivo."""
    import re
    m = re.search(r"^# (.+)$", item.get("body", ""), re.MULTILINE)
    if m:
        return m.group(1).strip()
    aliases = item["data"].get("aliases")
    if isinstance(aliases, list) and aliases:
        return str(aliases[0])
    return item["path"].stem


def stale_decisions(temporal_root: Path = TEMPORAL, *, days: int = DEFAULT_DAYS_STALE,
                    now: Optional[datetime] = None) -> list[dict]:
    """[{title, source_file, age_days, project, flagged}] ordenado por idade desc."""
    items = []
    for n in scan_neuronios(temporal_root, now=now):
        if n["type"] not in DECISION_TYPES or n["age_days"] is None:
            continue
        if n["age_days"] <= days:
            continue
        items.append({
            "title": _title(n),
            "source_file": str(n["path"]),
            "age_days": round(n["age_days"]),
            "project": n["project"],
            "flagged": n["staleness"] == "flagged",
        })
    return sorted(items, key=lambda x: -x["age_days"])


def render_markdown(items: list[dict]) -> str:
    """Tabela markdown p/ embutir no weekly / Ínsula. Vazio = mensagem amigável."""
    if not items:
        return "_Nenhuma decisão estagnada (> limiar). 👍_\n"
    lines = ["| Decisão | Projeto | Idade (dias) | Flag |",
             "|---|---|---:|:---:|"]
    for it in items:
        flag = "⚠️" if it["flagged"] else ""
        lines.append(f"| {it['title']} | {it['project']} | {it['age_days']} | {flag} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Relatório read-only de decisões estagnadas.")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS_STALE)
    args = ap.parse_args()
    items = stale_decisions(days=args.days)
    print(f"# Decisões estagnadas (> {args.days}d): {len(items)}\n")
    print(render_markdown(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
