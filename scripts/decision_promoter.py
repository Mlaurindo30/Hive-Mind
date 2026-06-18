#!/usr/bin/env python3
"""
scripts/decision_promoter.py — Promove decisões ao lobo frontal (Memória Viva F4.1).

Materializa cada neurônio `type: decision` (em cortex/temporal/) como um REGISTRO DE
DECISÃO em cortex/frontal/decisoes/{projeto}/dec-{hash}.md, com a estrutura do §5.2
(Contexto/Decisão/Rationale/Alternativas/Consequências) e wikilink ao neurônio de origem.

Idempotente (id determinístico `dec-{integrity_hash}`; bloco auto regenerável preserva
edição manual). Default = LOG-ONLY; só escreve com --apply. Opera nos ARQUIVOS
(frontmatter — R1/R2), reusando drift_detector.scan_neuronios. Sem LLM (v1).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from core.paths import DECISIONS_ROOT, TEMPORAL  # noqa: E402
from scripts.drift_detector import scan_neuronios, DECISION_TYPES  # noqa: E402

AUTO = "<!-- auto:gerado por decision_promoter.py — não editar dentro do bloco -->"


def _title(item: dict) -> str:
    m = re.search(r"^# (.+)$", item.get("body", ""), re.MULTILINE)
    if m:
        return m.group(1).strip()
    aliases = item["data"].get("aliases")
    if isinstance(aliases, list) and aliases:
        return str(aliases[0])
    return item["path"].stem


def _section(body: str, header: str) -> Optional[str]:
    """Extrai o conteúdo de uma seção '## header' do corpo, se existir."""
    m = re.search(rf"^##+\s*{re.escape(header)}\s*\n(.+?)(?=\n##\s|\Z)", body,
                  re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def promotable_decisions(temporal_root: Path = TEMPORAL, *, now=None) -> list[dict]:
    """Neurônios type=decision elegíveis a virar registro no frontal."""
    out = []
    for n in scan_neuronios(temporal_root, now=now):
        if n["type"] in DECISION_TYPES:
            out.append(n)
    return out


def _record_body(item: dict) -> str:
    title = _title(item)
    h = str(item["data"].get("integrity_hash", item["path"].stem))
    body = item.get("body", "")
    # "Decisão" = corpo principal (sem o H1); seções extras se existirem no neurônio.
    decisao = re.sub(r"^# .+?\n", "", body, count=1).strip()
    decisao = re.split(r"\n##\s", decisao)[0].strip() or "_(ver neurônio de origem)_"
    contexto = _section(body, "Contexto") or _section(body, "Context") or "_(a preencher)_"
    rationale = _section(body, "Rationale") or "_(a preencher)_"
    alternativas = _section(body, "Alternativas") or _section(body, "Alternatives") or "_(a preencher)_"
    consequencias = _section(body, "Consequências") or _section(body, "Consequences") or "_(a preencher)_"
    return f"""---
type: decision-record
project: {item['project']}
source_hash: {h}
status: open
promoted_by: scripts/decision_promoter.py
---
# Decisão: {title}

{AUTO}
> Origem: [[{item['path'].stem}]] · projeto _{item['project']}_

## Contexto
{contexto}

## Decisão
{decisao}

## Rationale
{rationale}

## Alternativas Consideradas
{alternativas}

## Consequências
{consequencias}
"""


def promote(item: dict, decisions_root: Path = DECISIONS_ROOT, *, dry_run: bool = True) -> Path:
    """Materializa um registro de decisão. Retorna o path (idempotente)."""
    h = str(item["data"].get("integrity_hash", item["path"].stem))
    dest = decisions_root / item["project"] / f"dec-{h}.md"
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_record_body(item), encoding="utf-8")
    return dest


def run(*, temporal_root: Path = TEMPORAL, decisions_root: Path = DECISIONS_ROOT,
        apply: bool = False) -> dict:
    items = promotable_decisions(temporal_root)
    for it in items:
        dest = promote(it, decisions_root, dry_run=not apply)
        print(f"  {'[apply]' if apply else '[dry]'} decisão → {dest}")
    stats = {"decisions": len(items), "applied": apply}
    print(f"decision_promoter: {stats}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Promove decisões ao lobo frontal (frontal/decisoes).")
    ap.add_argument("--apply", action="store_true", help="escreve (default: log-only)")
    args = ap.parse_args()
    run(apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
