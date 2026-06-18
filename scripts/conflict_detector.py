#!/usr/bin/env python3
"""
scripts/conflict_detector.py — Detecção de contradições (Memória Viva F4.4).

Acha pares de neurônios semanticamente próximos (fastembed) e usa o LLM (papel
'conflict_detector') para julgar se de fato se contradizem. Lista os conflitos em
cortex/insula/conflitos/{data}.md para revisão humana. READ-ONLY nos neurônios.

Boundedness: cap de pares candidatos por execução. Default = LOG-ONLY; --apply escreve.
Funções recebem embed_fn/llm_fn injetáveis (testável sem rede/modelo). load_env só na
execução (R3).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from core.paths import CONFLICTS_ROOT, TEMPORAL  # noqa: E402
from core.schemas.conflict_models import ConflictJudgement  # noqa: E402
from scripts.drift_detector import scan_neuronios  # noqa: E402

SIM_THRESHOLD = float(os.environ.get("HIVE_CONFLICT_THRESHOLD", "0.82"))
MAX_PAIRS = int(os.environ.get("HIVE_MAX_CONFLICT_PAIRS", "50"))


def _text(n: dict) -> str:
    import re
    body = n.get("body", "")
    title = ""
    m = re.search(r"^# (.+)$", body, re.MULTILINE)
    if m:
        title = m.group(1)
    return f"{title}\n{body}"[:600]


def _default_embed(texts: list[str]):
    from fastembed import TextEmbedding
    import numpy as np
    model = TextEmbedding()
    embs = [e / (np.linalg.norm(e) + 1e-9) for e in model.embed(texts)]
    return embs


def find_candidate_pairs(neurons: list[dict], *, threshold: float = SIM_THRESHOLD,
                         cap: int = MAX_PAIRS, embed_fn: Optional[Callable] = None) -> list[tuple]:
    """Pares (i, j, sim) com similaridade ≥ threshold, ordenados desc, limitados a cap."""
    if len(neurons) < 2:
        return []
    embs = (embed_fn or _default_embed)([_text(n) for n in neurons])
    pairs = []
    for i in range(len(neurons)):
        for j in range(i + 1, len(neurons)):
            sim = float(sum(a * b for a, b in zip(embs[i], embs[j])))
            if sim >= threshold:
                pairs.append((i, j, sim))
    pairs.sort(key=lambda x: -x[2])
    return pairs[:cap]


def _default_judge(a: dict, b: dict) -> ConflictJudgement:
    from core.auth import load_env
    from core.llm_client import call_llm_with_fallback
    load_env()
    return call_llm_with_fallback(
        role="conflict_detector",
        prompt=f"NOTA A:\n{_text(a)}\n\nNOTA B:\n{_text(b)}\n\nElas se contradizem?",
        system_prompt="Você detecta CONTRADIÇÕES factuais entre duas notas. Responda "
                      "is_conflict=true só se houver contradição real (não só temas próximos).",
        response_model=ConflictJudgement,
    )


def judge_conflict(a: dict, b: dict, *, llm_fn: Optional[Callable] = None) -> Optional[dict]:
    j = (llm_fn or _default_judge)(a, b)
    if not j.is_conflict:
        return None
    return {"a": a["path"].stem, "b": b["path"].stem,
            "a_project": a["project"], "b_project": b["project"],
            "explanation": j.explanation}


def write_report(conflicts: list[dict], conflicts_root: Path = CONFLICTS_ROOT, *,
                 dry_run: bool = True, now: Optional[datetime] = None) -> Path:
    now = now or datetime.now()
    dest = conflicts_root / f"{now.strftime('%Y-%m-%d')}.md"
    if not dry_run:
        conflicts_root.mkdir(parents=True, exist_ok=True)
        if conflicts:
            rows = "\n".join(
                f"- [[{c['a']}]] _({c['a_project']})_ ⚔️ [[{c['b']}]] _({c['b_project']})_ — {c['explanation']}"
                for c in conflicts)
        else:
            rows = "_Nenhum conflito detectado. 👍_"
        dest.write_text(f"""---
type: conflict-report
date: {now.strftime('%Y-%m-%d')}
count: {len(conflicts)}
---
# Conflitos de Memória — {now.strftime('%Y-%m-%d')}

<!-- auto:gerado por conflict_detector.py -->
{rows}
""", encoding="utf-8")
    return dest


def run(*, temporal_root: Path = TEMPORAL, conflicts_root: Path = CONFLICTS_ROOT,
        apply: bool = False, threshold: float = SIM_THRESHOLD, cap: int = MAX_PAIRS,
        embed_fn=None, llm_fn=None) -> dict:
    neurons = scan_neuronios(temporal_root)
    pairs = find_candidate_pairs(neurons, threshold=threshold, cap=cap, embed_fn=embed_fn)
    conflicts = []
    for i, j, sim in pairs:
        c = judge_conflict(neurons[i], neurons[j], llm_fn=llm_fn)
        if c:
            c["sim"] = round(sim, 3)
            conflicts.append(c)
    dest = write_report(conflicts, conflicts_root, dry_run=not apply)
    stats = {"neurons": len(neurons), "candidate_pairs": len(pairs),
             "conflicts": len(conflicts), "applied": apply, "report": str(dest)}
    print(f"conflict_detector: {stats}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Detecta contradições entre neurônios (insula/conflitos).")
    ap.add_argument("--apply", action="store_true", help="escreve o relatório (default: log-only)")
    ap.add_argument("--threshold", type=float, default=SIM_THRESHOLD)
    ap.add_argument("--cap", type=int, default=MAX_PAIRS)
    args = ap.parse_args()
    run(apply=args.apply, threshold=args.threshold, cap=args.cap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
