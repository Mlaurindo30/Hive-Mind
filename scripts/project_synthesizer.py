#!/usr/bin/env python3
"""
scripts/project_synthesizer.py — Status agregado por projeto (Memória Viva F4.2).

Gera/atualiza cortex/frontal/projetos/{projeto}.md com o status do projeto: nº de
neurônios, decisões, fatos, tópicos e último update. Bloco auto:start/end (idempotente)
preserva qualquer edição manual fora dele. File-based (frontmatter — R1/R2), sem LLM (v1).

Default = LOG-ONLY; só escreve com --apply.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from core.paths import PROJECTS_ROOT, TEMPORAL  # noqa: E402
from scripts.drift_detector import scan_neuronios, DECISION_TYPES  # noqa: E402

AUTO_START = "<!-- auto:start -->"
AUTO_END = "<!-- auto:end -->"


def project_stats(temporal_root: Path = TEMPORAL, *, now=None) -> dict:
    """{projeto: {neurons, decisions, facts, topics:[...], latest}}."""
    acc: dict = defaultdict(lambda: {"neurons": 0, "decisions": 0, "facts": 0,
                                     "topics": set(), "latest": None})
    for n in scan_neuronios(temporal_root, now=now):
        s = acc[n["project"]]
        s["neurons"] += 1
        if n["type"] in DECISION_TYPES:
            s["decisions"] += 1
        elif n["type"] == "fact":
            s["facts"] += 1
        s["topics"].add(n["topic"])
        lu = n["data"].get("last_updated")
        if lu and (s["latest"] is None or str(lu) > str(s["latest"])):
            s["latest"] = str(lu)
    return {p: {**v, "topics": sorted(v["topics"])} for p, v in acc.items()}


def _auto_block(project: str, st: dict) -> str:
    topics = "\n".join(f"- [[_{t}|{t}]]" for t in st["topics"]) or "- _(nenhum)_"
    return f"""{AUTO_START}
> Atualizado automaticamente por project_synthesizer.py · não editar dentro do bloco.

| Métrica | Valor |
|---|---|
| Neurônios | {st['neurons']} |
| Decisões | {st['decisions']} |
| Fatos | {st['facts']} |
| Tópicos | {len(st['topics'])} |
| Último update | {st['latest'] or 'n/a'} |

## Tópicos
{topics}
{AUTO_END}"""


def render(project: str, st: dict, existing: Optional[str] = None) -> str:
    """Render idempotente: substitui só o bloco auto, preservando edição manual."""
    block = _auto_block(project, st)
    if existing and AUTO_START in existing:
        return re.sub(re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END),
                      block, existing, flags=re.DOTALL)
    return f"""---
type: project-status
project: {project}
---
# 🧠 {project}

{block}

## Notas (manuais — preservadas)
"""


def write_all(*, temporal_root: Path = TEMPORAL, projects_root: Path = PROJECTS_ROOT,
              apply: bool = False, now=None) -> dict:
    stats = project_stats(temporal_root, now=now)
    for proj, st in sorted(stats.items()):
        dest = projects_root / f"{proj}.md"
        existing = dest.read_text(encoding="utf-8") if dest.exists() else None
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(render(proj, st, existing), encoding="utf-8")
        print(f"  {'[apply]' if apply else '[dry]'} {proj}: {st['neurons']} neurônios, {st['decisions']} decisões → {dest}")
    out = {"projects": len(stats), "applied": apply}
    print(f"project_synthesizer: {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Status agregado por projeto (frontal/projetos).")
    ap.add_argument("--apply", action="store_true", help="escreve (default: log-only)")
    args = ap.parse_args()
    write_all(apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
