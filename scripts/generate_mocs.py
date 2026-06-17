#!/usr/bin/env python3
"""
generate_mocs.py — Camada de NAVEGAÇÃO do cérebro (MOCs + sinapses) — §7.6.

Gera/atualiza, de forma idempotente, os Maps of Content que transformam o graph
view do Obsidian de "pontos soltos" em clusters conectados (hubs):

  _Consciencia.md                          (Home global — o "eu")
  cortex/temporal/<proj>/_<proj>.md        (MOC do projeto = lobo)
  cortex/temporal/<proj>/<top>/_<top>.md   (MOC do tópico)
  diencefalo/setores/_<setor>.md           (MOC de setor — cruza projetos)

Com --synapses: adiciona `related:` (WikiLinks) entre neurônios próximos
(cosine ≥ THRESHOLD via fastembed). MOCs são 100% auto-gerados (regeneráveis).

Uso:
  python scripts/generate_mocs.py              # só MOCs (rápido, sem modelo)
  python scripts/generate_mocs.py --synapses   # + sinapses por similaridade
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import paths as cp  # noqa: E402

SIM_THRESHOLD = 0.82
TOP_K = 3
AUTO = "<!-- auto:gerado por generate_mocs.py — não editar à mão -->"


def _title(md: Path) -> str:
    """Título do neurônio = 1ª linha '# ...' ou o nome do arquivo."""
    for ln in md.read_text(errors="ignore").splitlines():
        if ln.startswith("# "):
            return ln[2:].strip()
    return md.stem


def _frontmatter(md: Path) -> dict:
    txt = md.read_text(errors="ignore")
    m = re.match(r"^---\n(.*?)\n---", txt, re.S)
    fm = {}
    if m:
        for ln in m.group(1).splitlines():
            if ":" in ln:
                k, v = ln.split(":", 1)
                fm[k.strip()] = v.strip()
    return fm


def scan_neurons() -> list[dict]:
    """Lista neurônios (cortex/temporal/<proj>/<top>/*.md, exceto MOCs _*)."""
    out = []
    if not cp.TEMPORAL.exists():
        return out
    for md in cp.TEMPORAL.rglob("*.md"):
        if md.name.startswith("_"):
            continue
        rel = md.relative_to(cp.TEMPORAL).parts
        if len(rel) < 3:                       # precisa de proj/top/arquivo
            continue
        project, topic = rel[0], rel[1]
        fm = _frontmatter(md)
        sectors = [s.strip() for s in re.split(r"[,\[\]]", fm.get("sectors", "")) if s.strip()]
        out.append({"path": md, "project": project, "topic": topic,
                    "title": _title(md), "stem": md.stem, "sectors": sectors})
    return out


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def gen_topic_moc(project: str, topic: str, neurons: list[dict]) -> None:
    links = "\n".join(f"- [[{n['stem']}|{n['title']}]]" for n in sorted(neurons, key=lambda x: x['title']))
    _write(cp.topic_moc(project, topic), f"""---
type: moc
scope: topic
project: {project}
topic: {topic}
---
# {topic} — {project}

{AUTO}
> MOC do tópico · {len(neurons)} neurônio(s).

## Neurônios
{links}
""")


def gen_project_moc(project: str, by_topic: dict[str, list[dict]]) -> None:
    topics = "\n".join(
        f"- [[_{t}|{t}]] — {len(ns)} neurônio(s)"
        for t, ns in sorted(by_topic.items()))
    total = sum(len(ns) for ns in by_topic.values())
    _write(cp.project_moc(project), f"""---
type: moc
scope: project
project: {project}
---
# 🧠 {project}

{AUTO}
> Lobo-projeto · {len(by_topic)} tópico(s) · {total} neurônio(s).

## Tópicos
{topics}

## Voltar
- [[_Consciencia|🧠 Consciência]]
""")


def gen_sector_mocs(neurons: list[dict]) -> list[str]:
    by_sector: dict[str, list[dict]] = defaultdict(list)
    for n in neurons:
        for s in n["sectors"]:
            by_sector[s].append(n)
    for sector, ns in by_sector.items():
        links = "\n".join(
            f"- [[{n['stem']}|{n['title']}]] · _{n['project']}_"
            for n in sorted(ns, key=lambda x: x['title']))
        _write(cp.sector_moc(sector), f"""---
type: moc
scope: sector
sector: {sector}
---
# Setor: {sector}

{AUTO}
> Cruza projetos · {len(ns)} neurônio(s).

## Neurônios
{links}
""")
    return sorted(by_sector)


def gen_consciencia(by_project: dict[str, list[dict]], sectors: list[str]) -> None:
    projs = "\n".join(
        f"- [[_{p}|{p}]] — {len(ns)} neurônio(s)"
        for p, ns in sorted(by_project.items()))
    secs = "\n".join(f"- [[_{s}|{s}]]" for s in sectors) or "- _(nenhum ainda)_"
    _write(cp.CONSCIENCIA, f"""---
type: moc
scope: root
---
# 🧠 Consciência

{AUTO}
> Home do cérebro. Workspace global — o "eu" que integra os lobos.

## Projetos (lobo temporal — memória)
{projs}

## Setores (diencéfalo — relay cross-projeto)
{secs}

## Lobos
- **Frontal** — decisões, projetos, trabalho → `cortex/frontal/`
- **Parietal** — sensorial (inbox, referências) → `cortex/parietal/`
- **Occipital** — visão (capturas, grafo) → `cortex/occipital/`
- **Ínsula** — saúde/autoconsciência → `cortex/insula/`
- **Cerebelo** — ritmo (diário/sessões/semanal) → `cerebelo/`
- **Tronco** — infra vital → `tronco/`
""")


def add_synapses(neurons: list[dict]) -> int:
    """Escreve `related: [[...]]` no frontmatter de cada neurônio, ligando aos
    TOP_K mais similares (cosine ≥ SIM_THRESHOLD) via fastembed."""
    from fastembed import TextEmbedding
    import numpy as np
    model = TextEmbedding()   # default: BAAI/bge-small ou all-MiniLM (fastembed)
    texts = [n["path"].read_text(errors="ignore")[:2000] for n in neurons]
    embs = list(model.embed(texts))
    embs = [e / (np.linalg.norm(e) + 1e-9) for e in embs]
    written = 0
    for i, n in enumerate(neurons):
        sims = [(j, float(embs[i] @ embs[j])) for j in range(len(neurons)) if j != i]
        top = [neurons[j] for j, s in sorted(sims, key=lambda x: -x[1])[:TOP_K] if s >= SIM_THRESHOLD]
        if not top:
            continue
        rel = ", ".join(f'"[[{t["stem"]}]]"' for t in top)
        txt = n["path"].read_text(errors="ignore")
        if "related:" in txt:
            txt = re.sub(r"related:.*", f"related: [{rel}]", txt, count=1)
        else:
            txt = re.sub(r"^---\n", f"---\nrelated: [{rel}]\n", txt, count=1)
        n["path"].write_text(txt)
        written += 1
    return written


def build_mocs(verbose: bool = True) -> dict:
    """Gera todos os MOCs (rápido, sem modelo). Idempotente. Retorna contadores.
    Chamável pelo dream_cycle ao fim de cada ciclo."""
    neurons = scan_neurons()
    by_project: dict[str, list[dict]] = defaultdict(list)
    by_proj_topic: dict[tuple, list[dict]] = defaultdict(list)
    for n in neurons:
        by_project[n["project"]].append(n)
        by_proj_topic[(n["project"], n["topic"])].append(n)
    for (proj, top), ns in by_proj_topic.items():
        gen_topic_moc(proj, top, ns)
    for proj, ns in by_project.items():
        bt = defaultdict(list)
        for n in ns:
            bt[n["topic"]].append(n)
        gen_project_moc(proj, bt)
    sectors = gen_sector_mocs(neurons)
    gen_consciencia(by_project, sectors)
    stats = {"neurons": len(neurons), "projects": len(by_project),
             "topics": len(by_proj_topic), "sectors": len(sectors)}
    if verbose:
        print(f"  MOCs: 1 consciência + {stats['projects']} projeto(s) + "
              f"{stats['topics']} tópico(s) + {stats['sectors']} setor(es)")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synapses", action="store_true", help="também gera related: por similaridade")
    args = ap.parse_args()
    neurons = scan_neurons()
    print(f"=== {len(neurons)} neurônios encontrados ===")
    build_mocs()
    if args.synapses:
        n = add_synapses(neurons)
        print(f"  Sinapses: related: escrito em {n} neurônio(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
