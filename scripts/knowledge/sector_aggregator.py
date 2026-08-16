#!/usr/bin/env python3
"""Agrega sectores cross-project no diencefalo/setores/.

F3 (2026-08-13): o sector_classifier escreve `sectors:` no frontmatter dos
neurônios (temporal), mas NENHUM script agrega isso no diencefalo/setores/ —
a função canônica do diencefalo é "Relay cross-projeto: conecta conhecimento
que atravessa múltiplos projetos".

Este script lê todos os neurônios com `sectors:` e gera, para cada sector
canônico (ai-infra, dev-tools, pkm, infra, finance, health, research), um
`setor-<n>.md` no diencefalo listando os neurônios cross-project daquele setor.

Determinístico (sem LLM): só agrega o que o sector_classifier já classificou.

Uso:
    python scripts/knowledge/sector_aggregator.py --dry-run
    python scripts/knowledge/sector_aggregator.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent.parent
sys.path.insert(0, str(ROOT))

from core import paths as cp  # noqa: E402

SECTOR_NAMES = {
    "ai-infra": "Infraestrutura de IA",
    "dev-tools": "Ferramentas de Desenvolvimento",
    "pkm": "Personal Knowledge Management",
    "infra": "Infraestrutura Geral",
    "finance": "Finanças",
    "health": "Saúde",
    "research": "Pesquisa",
}


def _scan_sectors(temporal: Path) -> dict[str, dict]:
    """{sector: {project: [neuronios...]}}."""
    acc: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for f in temporal.rglob("neuronio-*.md"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # extrai frontmatter
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not m:
            continue
        fm = m.group(1)
        sect_m = re.search(r"^sectors:\s*\n((?:\s*-\s*.+\n?)+)", fm, re.MULTILINE)
        if not sect_m:
            # formato inline: sectors: [a, b]
            sect_inline = re.search(r"^sectors:\s*\[(.*?)\]", fm, re.MULTILINE)
            if not sect_inline:
                continue
            sectors = [s.strip().strip('"\'') for s in sect_inline.group(1).split(",")]
        else:
            sectors = [re.sub(r"^\s*-\s*", "", line).strip() for line in sect_m.group(1).splitlines() if line.strip().startswith("-")]
        # project
        proj_m = re.search(r"^project:\s*(.+)$", fm, re.MULTILINE)
        project = proj_m.group(1).strip() if proj_m else "unclassified"
        for s in sectors:
            if s and s in SECTOR_NAMES:
                acc[s][project].append(f.stem)
    return acc


def _sector_body(sector: str, data: dict, idx: int) -> str:
    name = SECTOR_NAMES.get(sector, sector)
    total = sum(len(v) for v in data.values())
    lines = [
        "---",
        "type: sector",
        f"sector: {sector}",
        f"sector_name: {name}",
        f"neurons: {total}",
        "---",
        f"# {name} ({sector})",
        "",
        f"> Relay cross-projeto — {total} neurônios de {len(data)} projetos.",
        "",
    ]
    for project in sorted(data, key=lambda p: -len(data[p])):
        lines.append(f"## {project}")
        for stem in sorted(set(data[project]))[:50]:  # cap defensivo
            lines.append(f"- [[{stem}]]")
        lines.append("")
    lines.extend([
        "## Sinapses",
        "- lobo:: [[diencefalo]]",
        "- córtex:: [[cortex]]",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Agrega sectores no diencefalo/setores/")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    data = _scan_sectors(cp.TEMPORAL)
    sectors_root = cp.SECTORS_ROOT

    idx = 1
    for sector in sorted(data, key=lambda s: -sum(len(v) for v in data[s].values())):
        body = _sector_body(sector, data[sector], idx)
        dest = sectors_root / f"setor-{idx}.md"
        if args.apply:
            sectors_root.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8")
        total = sum(len(v) for v in data[sector].values())
        print(f"  setor-{idx} {sector}: {total} neurônios, {len(data[sector])} projetos")
        idx += 1

    if not data:
        print("Nenhum neurônio com sectors encontrado. Rode o sector_classifier primeiro.")
        return 1
    if not args.apply:
        print("\n[dry-run] use --apply para escrever")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
