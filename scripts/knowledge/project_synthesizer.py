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
sys.path.insert(0, str(_HERE.parent.parent))

from core.paths import PROJECTS_ROOT, TEMPORAL  # noqa: E402
from core.vault import project_display_name, canonical_slug  # noqa: E402
from scripts.knowledge.drift_detector import scan_neuronios, DECISION_TYPES  # noqa: E402

AUTO_START = "<!-- auto:start -->"
AUTO_END = "<!-- auto:end -->"

# F2.3 (2026-08-13): limita a lista de tópicos no bloco auto. O bug anterior
# listava TODOS os tópicos (centenas) criando "topic-junk" — wikilinks de slug
# sem valor navegacional. Mantemos só os N mais frequentes (relevância real).
MAX_TOPICS = 30


def project_stats(temporal_root: Path = TEMPORAL, *, now=None) -> dict:
    """{projeto: {neurons, decisions, facts, topics:{topico:count}, latest}}."""
    acc: dict = defaultdict(lambda: {"neurons": 0, "decisions": 0, "facts": 0,
                                     "topics": defaultdict(int), "latest": None})
    for n in scan_neuronios(temporal_root, now=now):
        s = acc[n["project"]]
        s["neurons"] += 1
        if n["type"] in DECISION_TYPES:
            s["decisions"] += 1
        elif n["type"] == "fact":
            s["facts"] += 1
        t = canonical_slug(n["topic"] or "general")
        s["topics"][t] += 1
        lu = n["data"].get("last_updated")
        if lu and (s["latest"] is None or str(lu) > str(s["latest"])):
            s["latest"] = str(lu)
    return {
        p: {**v, "topics": dict(sorted(v["topics"].items(), key=lambda kv: -kv[1])[:MAX_TOPICS])}
        for p, v in acc.items()
    }


def _auto_block(project: str, st: dict) -> str:
    # F2.3: wikilink correto (sem underscore fantasma), top N por frequência.
    topics = "\n".join(f"- [[{t}]] _({c})_" for t, c in st["topics"].items()) or "- _(nenhum)_"
    return f"""{AUTO_START}
> Atualizado automaticamente por project_synthesizer.py · não editar dentro do bloco.

| Métrica | Valor |
|---|---|
| Neurônios | {st['neurons']} |
| Decisões | {st['decisions']} |
| Fatos | {st['facts']} |
| Tópicos | {len(st['topics'])} |
| Último update | {st['latest'] or 'n/a'} |

## Tópicos principais
{topics}
{AUTO_END}"""


def render(project: str, st: dict, existing: Optional[str] = None) -> str:
    """Render idempotente: substitui só o bloco auto, preservando edição manual."""
    block = _auto_block(project, st)
    display = project_display_name(project)
    if existing and AUTO_START in existing:
        return re.sub(re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END),
                      block, existing, flags=re.DOTALL)
    return f"""---
type: project-status
project: {display}
project_id: {project}
---
# 🧠 {display}

{block}

## Sinapses
- projeto:: [[{display}]]
- lobo:: [[cortex-frontal]]
- córtex:: [[cortex]]

## Notas (manuais — preservadas)
"""


def write_all(*, temporal_root: Path = TEMPORAL, projects_root: Path = PROJECTS_ROOT,
              apply: bool = False, now=None) -> dict:
    stats = project_stats(temporal_root, now=now)
    for proj, st in sorted(stats.items()):
        # F2.3: nome de ARQUIVO usa o nome humano (project_display_name), não o
        # hash/workspace_id cru. Mantém o project_id real no frontmatter.
        display = project_display_name(proj)
        fname = canonical_slug(display) or proj
        dest = projects_root / f"{fname}.md"
        existing = dest.read_text(encoding="utf-8") if dest.exists() else None
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(render(proj, st, existing), encoding="utf-8")
        print(f"  {'[apply]' if apply else '[dry]'} {proj}: {st['neurons']} neurônios, {st['decisions']} decisões → {dest.name}")
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
