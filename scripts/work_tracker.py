#!/usr/bin/env python3
"""
scripts/work_tracker.py — Trabalho ativo (Memória Viva F4.5, opcional).

Extrai os "Próximos Passos" das session-logs recentes (cerebelo/sessoes) e materializa
um quadro de trabalho ativo em cortex/frontal/trabalho/ativo/_ativo.md. Idempotente
(regenera do estado atual). File-based, sem LLM. Default = LOG-ONLY; --apply escreve.
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

from core.paths import SESSIONS_ROOT, WORK_ACTIVE  # noqa: E402

# Captura bullets sob um header "Próximos Passos" (ou "Next Steps") até o próximo header.
_NEXT_RE = re.compile(r"^##+\s*(?:Próximos Passos|Proximos Passos|Next Steps)\s*\n(.+?)(?=\n##\s|\Z)",
                      re.MULTILINE | re.DOTALL | re.IGNORECASE)


def extract_next_steps(sessions_root: Path = SESSIONS_ROOT, *, since_days: int = 14,
                       now: Optional[datetime] = None) -> list[dict]:
    """[{item, session}] dos 'Próximos Passos' das sessões recentes (não concluídos)."""
    if not sessions_root.exists():
        return []
    now = now or datetime.now()
    cutoff = now.timestamp() - since_days * 86400
    out: list[dict] = []
    seen: set[str] = set()
    for f in sorted(sessions_root.rglob("*.md"), key=lambda p: -p.stat().st_mtime):
        if f.stat().st_mtime < cutoff:
            continue
        m = _NEXT_RE.search(f.read_text(errors="ignore"))
        if not m:
            continue
        for line in m.group(1).splitlines():
            b = re.match(r"\s*[-*]\s+(.*\S)", line)
            if not b:
                continue
            item = b.group(1).strip()
            # Ignora itens já marcados como feitos ([x]) e duplicatas.
            if item.lower().startswith(("[x]", "~~")) or item in seen:
                continue
            seen.add(item)
            out.append({"item": item, "session": f.stem})
    return out


def render(items: list[dict], *, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    rows = "\n".join(f"- [ ] {it['item']}  ·  _{it['session']}_" for it in items) \
        or "- _(nenhum item ativo)_"
    return f"""---
type: work-active
updated: {now.strftime('%Y-%m-%d')}
count: {len(items)}
---
# Trabalho Ativo

<!-- auto:gerado por work_tracker.py — itens vêm dos 'Próximos Passos' das sessões -->
{rows}
"""


def run(*, sessions_root: Path = SESSIONS_ROOT, work_active: Path = WORK_ACTIVE,
        apply: bool = False, since_days: int = 14, now: Optional[datetime] = None) -> dict:
    items = extract_next_steps(sessions_root, since_days=since_days, now=now)
    dest = work_active / "_ativo.md"
    if apply:
        work_active.mkdir(parents=True, exist_ok=True)
        dest.write_text(render(items, now=now), encoding="utf-8")
    stats = {"items": len(items), "applied": apply, "dest": str(dest)}
    print(f"work_tracker: {stats}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Quadro de trabalho ativo (frontal/trabalho/ativo).")
    ap.add_argument("--apply", action="store_true", help="escreve (default: log-only)")
    ap.add_argument("--since-days", type=int, default=14)
    args = ap.parse_args()
    run(apply=args.apply, since_days=args.since_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
