#!/usr/bin/env python3
"""
scripts/decision_promoter.py — Promove decisões ao lobo frontal (Memória Viva F4.1).

Materializa cada neurônio `type: decision` (em cortex/temporal/) como um REGISTRO DE
DECISÃO em cortex/frontal/decisoes/{projeto}/dec-{hash}.md, com a estrutura do §5.2
(Contexto/Decisão/Rationale/Alternativas/Consequências) e wikilink ao neurônio de origem.

Idempotente (id determinístico `dec-{integrity_hash}`; bloco auto regenerável preserva
edição manual). Default = LOG-ONLY; só escreve com --apply. Opera nos ARQUIVOS
(frontmatter — R1/R2), reusando drift_detector.scan_neuronios.

F2.1 (2026-08-13) — v2: quando o neurônio de origem NÃO tem as seções
Contexto/Rationale/Alternativas/Consequências (caso dos neurônios K3), usa o LLM
(papel `decision_promoter`, herda do dreamer) para GERAR essas seções a partir do
corpo — em vez de escrever "_(a preencher)_". Controlado por --with-llm (off por
padrão, para manter o modo determinístico/log-only como fallback).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from core.paths import DECISIONS_ROOT, TEMPORAL  # noqa: E402
from core.knowledge.intake import KnowledgeCandidate, build_candidate  # noqa: E402
from scripts.knowledge.drift_detector import scan_neuronios, DECISION_TYPES  # noqa: E402

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


def _fill_via_llm(decisao: str, title: str) -> dict[str, str]:
    """F2.1: gera Contexto/Rationale/Alternativas/Consequências via LLM.

    Usa `call_llm_with_fallback` (gateway com fallback) — NÃO `call_llm_role` do
    dream_cycle, que chama o provider explícito (gemini-cli) sem fallback e
    falha quando o gemini-cli não está instalado. O gateway roteia para o
    ollama/granite4.1:8b local quando o primário falha.
    """
    try:
        from core.auth import load_env
        from core.llm_client import call_llm_with_fallback
        from core.schemas.dream_models import DecisionRationaleOutput
        load_env()
    except Exception:
        return {}

    prompt = f"DECISÃO:\n{title}\n\nCONTEÚDO:\n{decisao}\n"
    try:
        out = call_llm_with_fallback(
            "decision_promoter", prompt, _DECISION_PROMPT, DecisionRationaleOutput
        )
        if out is None:
            return {}
        return {
            "contexto": getattr(out, "contexto", "") or "",
            "rationale": getattr(out, "rationale", "") or "",
            "alternativas": getattr(out, "alternativas", "") or "",
            "consequencias": getattr(out, "consequencias", "") or "",
        }
    except Exception:
        return {}


_DECISION_PROMPT = (
    "Você analisa uma decisão técnica e produz 4 campos concisos (2-3 linhas cada):\n"
    "  contexto: o que motivou a decisão (problema/restrição).\n"
    "  rationale: por que essa opção foi escolhida (trade-off).\n"
    "  alternativas: o que foi considerado e rejeitado.\n"
    "  consequencias: o impacto esperado.\n"
    "Não invente fatos que não estão no conteúdo. Se não houver evidência, deixe o campo vazio."
)


def promotable_decisions(temporal_root: Path = TEMPORAL, *, now=None) -> list[dict]:
    """Neurônios type=decision elegíveis a virar registro no frontal."""
    out = []
    for n in scan_neuronios(temporal_root, now=now):
        if n["type"] in DECISION_TYPES:
            out.append(n)
    return out


def _record_body(item: dict, *, with_llm: bool = False) -> str:
    title = _title(item)
    h = str(item["data"].get("integrity_hash", item["path"].stem))
    body = item.get("body", "")
    # "Decisão" = corpo principal (sem o H1); seções extras se existirem no neurônio.
    decisao = re.sub(r"^# .+?\n", "", body, count=1).strip()
    decisao = re.split(r"\n##\s", decisao)[0].strip() or "_(ver neurônio de origem)_"
    contexto = _section(body, "Contexto") or _section(body, "Context")
    rationale = _section(body, "Rationale")
    alternativas = _section(body, "Alternativas") or _section(body, "Alternatives")
    consequencias = _section(body, "Consequências") or _section(body, "Consequences")

    # F2.1: se faltar seção e --with-llm, gera via LLM.
    missing = any(not x for x in (contexto, rationale, alternativas, consequencias))
    if with_llm and missing:
        filled = _fill_via_llm(decisao, title)
        contexto = contexto or filled.get("contexto") or ""
        rationale = rationale or filled.get("rationale") or ""
        alternativas = alternativas or filled.get("alternativas") or ""
        consequencias = consequencias or filled.get("consequencias") or ""

    contexto = contexto or "_(a preencher)_"
    rationale = rationale or "_(a preencher)_"
    alternativas = alternativas or "_(a preencher)_"
    consequencias = consequencias or "_(a preencher)_"

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

## Sinapses
- projeto:: [[{item['project']}]]
- lobo:: [[cortex-frontal]]
- córtex:: [[cortex]]
"""


def promote(item: dict, decisions_root: Path = DECISIONS_ROOT, *,
            dry_run: bool = True, with_llm: bool = False) -> Path:
    """Materializa um registro de decisão. Retorna o path (idempotente).

    FIX (2026-08-13): idempotência real. Se o arquivo já existe e NÃO tem o
    placeholder "_(a preencher)_", NÃO reescreve — preserva o conteúdo já
    preenchido por um backfill anterior (e evita que o consolidate_loop desfaça
    o trabalho ao re-rodar sem --with-llm).
    """
    h = str(item["data"].get("integrity_hash", item["path"].stem))
    dest = decisions_root / item["project"] / f"dec-{h}.md"
    if not dry_run:
        # Idempotência real (FIX 2026-08-14): só reescreve se (a) o arquivo ainda
        # tem placeholder E (b) a fonte mudou desde a última gravação. Antes, a
        # condição "só escreve se NÃO tem placeholder" fazia o loop infinito: quando
        # o LLM não consegue preencher conteúdo casca (ex.: "Test"/"Linha 1"), o
        # placeholder permanece e o arquivo era reescrito a cada ciclo MEDIUM.
        if dest.exists():
            has_placeholder = "_(a preencher)_" in dest.read_text(encoding="utf-8", errors="replace")
            src_newer = False
            try:
                src = item.get("path")
                src_mtime = Path(src).stat().st_mtime if src else 0.0
                src_newer = src_mtime > dest.stat().st_mtime
            except OSError:
                src_newer = True
            if not has_placeholder or not src_newer:
                return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_record_body(item, with_llm=with_llm), encoding="utf-8")
    return dest


def collect_candidates(temporal_root: Path = TEMPORAL, *, workspace_id: str = "default") -> list[KnowledgeCandidate]:
    """Candidate-only view for K3 orchestration; no file writes."""
    out: list[KnowledgeCandidate] = []
    for item in promotable_decisions(temporal_root):
        title = _title(item)
        content = re.sub(r"^# .+?\n", "", item.get("body", ""), count=1).strip() or title
        out.append(build_candidate(
            source_type="decision_promoter",
            source_id=str(item["path"]),
            knowledge_type="decision",
            title=title,
            content=content,
            project=item["project"],
            workspace_id=workspace_id,
            evidence={
                "source_uri": str(item["path"]),
                "source_hash": str(item["data"].get("integrity_hash", "")),
            },
            metadata={"promoter": "decision_promoter"},
        ))
    return out


def run(*, temporal_root: Path = TEMPORAL, decisions_root: Path = DECISIONS_ROOT,
        apply: bool = False, with_llm: bool = False) -> dict:
    items = promotable_decisions(temporal_root)
    # FIX (2026-08-13): mapeia hash → projeto ATUAL, para mover decisões órfãs
    # (em subpasta de projeto que mudou no saneamento: hash-puro→unclassified,
    # git→omniroute, etc.) para a subpasta correta.
    hash_to_project = {}
    for it in items:
        h = it["data"].get("integrity_hash")
        if h:
            hash_to_project[str(h)] = it["project"]

    for it in items:
        dest = promote(it, decisions_root, dry_run=not apply, with_llm=with_llm)
        print(f"  {'[apply]' if apply else '[dry]'} decisão → {dest}")

    # Migra decisões órfãs (subpasta antiga → subpasta do projeto atual).
    migrated = _migrate_orphan_decisions(decisions_root, hash_to_project, apply=apply)

    stats = {"decisions": len(items), "applied": apply, "with_llm": with_llm,
             "migrated": migrated}
    print(f"decision_promoter: {stats}")
    return stats


def _migrate_orphan_decisions(decisions_root: Path, hash_to_project: dict,
                              apply: bool = False) -> int:
    """Move decisões de subpastas órfãs para a subpasta do projeto atual.

    Após o saneamento do temporal (merge de variantes, hash-puro→unclassified),
    decisões já materializadas ficaram em subpastas de projetos que não existem
    mais. O `promote` idempotente só escreve na subpasta do projeto ATUAL, então
    as órfãs nunca são atualizadas. Este passo as move (por hash) para a subpasta
    correta e depois re-promove.
    """
    import re
    migrated = 0
    if not decisions_root.exists():
        return 0
    for sub in decisions_root.iterdir():
        if not sub.is_dir():
            continue
        for f in sub.glob("dec-*.md"):
            m = re.search(r"dec-([0-9a-f]{16})\.md", f.name)
            if not m:
                continue
            h = m.group(1)
            atual = hash_to_project.get(h)
            if atual is None or atual == sub.name:
                continue
            dest_dir = decisions_root / atual
            if not apply:
                migrated += 1
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f.name
            if not dest.exists():
                import shutil
                shutil.move(str(f), str(dest))
            else:
                # já existe no destino (idempotente) → remove a órfã
                f.unlink()
            migrated += 1
        # remove subpasta órfã vazia
        if apply and not any(sub.iterdir()):
            try:
                sub.rmdir()
            except OSError:
                pass
    return migrated


def main() -> int:
    ap = argparse.ArgumentParser(description="Promove decisões ao lobo frontal (frontal/decisoes).")
    ap.add_argument("--apply", action="store_true", help="escreve (default: log-only)")
    ap.add_argument("--with-llm", action="store_true",
                    help="F2.1: gera Contexto/Rationale/Alternativas/Consequências via LLM quando ausentes")
    args = ap.parse_args()
    run(apply=args.apply, with_llm=args.with_llm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

