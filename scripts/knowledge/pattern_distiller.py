#!/usr/bin/env python3
"""
scripts/pattern_distiller.py — Memória procedural (Memória Viva F4.3).

Destila "padrões que funcionaram" (sequências recorrentes de ação/decisão) das
session-logs (cerebelo/sessoes) e materializa em cerebelo/padroes/{slug}.md.

Usa o papel LLM 'pattern_distiller' (herda do dreamer = gemini-cli/Code Assist por
default). Boundedness: cap de sinais por execução. Idempotente (slug estável).
Default = LOG-ONLY; só escreve com --apply. load_env() só na execução (R3).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from core.paths import PADROES_ROOT, SESSIONS_ROOT  # noqa: E402
from core.knowledge.intake import KnowledgeCandidate, build_candidate  # noqa: E402
from core.schemas.pattern_models import PatternOutput, Pattern  # noqa: E402

MAX_SIGNAL_CHARS = int(__import__("os").environ.get("HIVE_MAX_SIGNAL_CHARS", "8000"))
SYSTEM_PROMPT = (
    "Você é um destilador de PADRÕES PROCEDURAIS. A partir de logs de sessões de "
    "trabalho, identifique padrões recorrentes do tipo 'o que funcionou' (sequências "
    "de ação/decisão reaproveitáveis). Para cada padrão dê título, slug kebab-case, "
    "contexto, passos e quando usar. Seja conservador: só padrões com evidência real. "
    "Responda no schema JSON fornecido."
)


def gather_signals(sessions_root: Path = SESSIONS_ROOT, *, since_days: int = 30,
                   now: Optional[datetime] = None, cap_chars: int = MAX_SIGNAL_CHARS) -> str:
    """Concatena conteúdo das session-logs recentes (bounded). '' se não houver."""
    if not sessions_root.exists():
        return ""
    now = now or datetime.now()
    cutoff = now.timestamp() - since_days * 86400
    chunks: list[str] = []
    total = 0
    for f in sorted(sessions_root.rglob("*.md"), key=lambda p: -p.stat().st_mtime):
        if f.stat().st_mtime < cutoff:
            continue
        txt = f.read_text(errors="ignore")
        chunks.append(f"### {f.name}\n{txt}")
        total += len(txt)
        if total >= cap_chars:
            break
    return "\n\n".join(chunks)[:cap_chars]


def distill_patterns(signals: str) -> PatternOutput:
    """Chama o LLM (papel pattern_distiller) p/ extrair padrões. '' → vazio (sem LLM)."""
    if not signals.strip():
        return PatternOutput(patterns=[])
    from core.auth import load_env
    from core.llm_client import call_llm_with_fallback
    load_env()
    return call_llm_with_fallback(
        role="pattern_distiller",
        prompt=f"LOGS DE SESSÃO:\n{signals}",
        system_prompt=SYSTEM_PROMPT,
        response_model=PatternOutput,
    )


def _slug(p: Pattern) -> str:
    base = (p.slug or p.title or "padrao").lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "padrao"


def write_pattern(p: Pattern, padroes_root: Path = PADROES_ROOT, *, dry_run: bool = True) -> Path:
    dest = padroes_root / f"{_slug(p)}.md"
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(p.steps, 1)) or "_(sem passos)_"
        dest.write_text(f"""---
type: pattern
slug: {_slug(p)}
confidence: {p.confidence}
---
# Padrão: {p.title}

<!-- auto:gerado por pattern_distiller.py -->
## Contexto
{p.context}

## Passos
{steps}

## Quando usar
{p.when_to_use or '_(a preencher)_'}
""", encoding="utf-8")
    return dest


def patterns_to_candidates(
    patterns: list[Pattern],
    *,
    project: str = "default",
    workspace_id: str = "default",
) -> list[KnowledgeCandidate]:
    """Candidate-only view for K3; converts distilled patterns to learnings."""
    candidates: list[KnowledgeCandidate] = []
    for p in patterns:
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(p.steps, 1))
        content = f"{p.context}\n\n## Passos\n{steps}\n\n## Quando usar\n{p.when_to_use or ''}".strip()
        candidates.append(build_candidate(
            source_type="pattern_distiller",
            source_id=_slug(p),
            knowledge_type="learning",
            title=p.title,
            content=content,
            project=project,
            workspace_id=workspace_id,
            evidence={"pattern_slug": _slug(p), "confidence": p.confidence},
            metadata={"promoter": "pattern_distiller", "slug": _slug(p)},
        ))
    return candidates


def run(*, sessions_root: Path = SESSIONS_ROOT, padroes_root: Path = PADROES_ROOT,
        apply: bool = False, since_days: int = 30) -> dict:
    signals = gather_signals(sessions_root, since_days=since_days)
    out = distill_patterns(signals)
    for p in out.patterns:
        dest = write_pattern(p, padroes_root, dry_run=not apply)
        print(f"  {'[apply]' if apply else '[dry]'} padrão → {dest}")
    stats = {"signals_chars": len(signals), "patterns": len(out.patterns), "applied": apply}
    print(f"pattern_distiller: {stats}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Destila padrões procedurais (cerebelo/padroes).")
    ap.add_argument("--apply", action="store_true", help="escreve (default: log-only)")
    ap.add_argument("--since-days", type=int, default=30)
    args = ap.parse_args()
    run(apply=args.apply, since_days=args.since_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
