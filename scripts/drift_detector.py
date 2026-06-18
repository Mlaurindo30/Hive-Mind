#!/usr/bin/env python3
"""
scripts/drift_detector.py — Envelhecimento de memória (Memória Viva, doc 08 / F3.1).

Marca neurônios antigos como FRIOS e sinaliza decisões estagnadas — sem apagar nada.
Idempotente (rodar 2× não muda nada). Default = LOG-ONLY; só escreve com --apply.

REGRAS:
  - átomo (type != decision/moc) com last_updated > N_cold dias (90)  → visibility: cold
    + move o arquivo p/ cortex/temporal/arquivo/{projeto}/{topico}/ (sai dos MOCs ativos).
  - decision com last_updated > N_stale dias (180)                    → staleness: flagged
    (NÃO move; continua visível, só sinalizada).

NOTA DE SCHEMA (R1/R2 do §14): a coluna `neurons.type` no hive_mind.db NÃO serve aqui —
os neurônios file-backed em cortex/temporal lá são type='document' (ingestão graphify).
A verdade de decision/fact e da idade vive no FRONTMATTER dos arquivos `neuronio-*.md`
(campo `last_updated`). Por isso este detector opera nos ARQUIVOS, igual alias_miner/
generate_mocs — não na tabela neurons. Sem LLM, sem load_env (zero efeito colateral, R3).
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import yaml  # noqa: E402
from core.paths import TEMPORAL, ARQUIVO  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("drift_detector")

DEFAULT_DAYS_COLD = 90
DEFAULT_DAYS_STALE = 180
MAX_DRIFT_PER_RUN = 200            # boundedness (R8): teto de itens por execução
DECISION_TYPES = {"decision"}
SKIP_TYPES = {"moc", "redirect"}   # navegação/redireExibido — nunca esfria


def parse_frontmatter(content: str) -> tuple[dict, str, str]:
    """(data, bloco_fm_incluindo_---, corpo). data={} se não houver frontmatter."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        return {}, "", content
    full, body = m.group(0), content[len(m.group(0)):]
    try:
        data = yaml.safe_load(m.group(1))
        return (data or {}), full, body
    except yaml.YAMLError:
        return {}, full, body


def _age_days(last_updated: Any, *, now: Optional[datetime] = None) -> Optional[float]:
    """Idade em dias a partir de `last_updated` (str 'YYYY-MM-DD[ HH:MM]' ou datetime)."""
    now = now or datetime.now()
    if last_updated is None:
        return None
    if isinstance(last_updated, datetime):
        return (now - last_updated).total_seconds() / 86400.0
    s = str(last_updated).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return (now - datetime.strptime(s[: len(fmt) + 2], fmt)).total_seconds() / 86400.0
        except ValueError:
            continue
    return None


def _project_topic(path: Path, temporal_root: Path) -> tuple[str, str]:
    """Deriva (projeto, topico) do caminho relativo a temporal_root."""
    rel = path.relative_to(temporal_root).parts
    project = rel[0] if len(rel) >= 1 else "_global"
    topic = rel[1] if len(rel) >= 3 else "_"
    return project, topic


def scan_neuronios(temporal_root: Path, *, now: Optional[datetime] = None) -> list[dict]:
    """Lista os neurônios (neuronio-*.md) com type/idade/projeto derivados do frontmatter."""
    out: list[dict] = []
    if not temporal_root.exists():
        return out
    for md in temporal_root.rglob("neuronio-*.md"):
        # Não reprocessa o que já está arquivado (idempotência).
        if "arquivo" in md.relative_to(temporal_root).parts[:1]:
            continue
        data, fm, body = parse_frontmatter(md.read_text(errors="ignore"))
        ntype = str(data.get("type", "")).strip().lower()
        project, topic = _project_topic(md, temporal_root)
        out.append({
            "path": md, "data": data, "fm": fm, "body": body, "type": ntype,
            "age_days": _age_days(data.get("last_updated"), now=now),
            "visibility": str(data.get("visibility", "")).strip().lower(),
            "staleness": str(data.get("staleness", "")).strip().lower(),
            "project": project, "topic": topic,
        })
    return out


def classify(neurons: list[dict], *, days_cold: int, days_stale: int) -> tuple[list, list]:
    """Separa (cold, stale) aplicando as regras. Não escreve nada."""
    cold, stale = [], []
    for n in neurons:
        age = n["age_days"]
        if age is None:
            continue
        if n["type"] in DECISION_TYPES:
            if age > days_stale and n["staleness"] != "flagged":
                stale.append(n)
        elif n["type"] not in SKIP_TYPES:
            if age > days_cold and n["visibility"] != "cold":
                cold.append(n)
    return cold, stale


def _rewrite(data: dict, body: str) -> str:
    return "---\n" + yaml.dump(data, allow_unicode=True, sort_keys=False) + "---\n" + body


def apply_cold(item: dict, arquivo_root: Path, *, dry_run: bool) -> Optional[Path]:
    """Marca visibility: cold e move p/ arquivo/{proj}/{topic}/. Retorna novo path."""
    dest_dir = arquivo_root / item["project"] / item["topic"]
    dest = dest_dir / item["path"].name
    if dry_run:
        return dest
    item["data"]["visibility"] = "cold"
    dest_dir.mkdir(parents=True, exist_ok=True)
    item["path"].write_text(_rewrite(item["data"], item["body"]), encoding="utf-8")
    item["path"].rename(dest)
    return dest


def apply_stale(item: dict, *, dry_run: bool) -> None:
    """Adiciona staleness: flagged no frontmatter (não move)."""
    if dry_run:
        return
    item["data"]["staleness"] = "flagged"
    item["path"].write_text(_rewrite(item["data"], item["body"]), encoding="utf-8")


def run_drift(*, temporal_root: Path = TEMPORAL, arquivo_root: Path = ARQUIVO,
              days_cold: int = DEFAULT_DAYS_COLD, days_stale: int = DEFAULT_DAYS_STALE,
              limit: int = MAX_DRIFT_PER_RUN, apply: bool = False,
              now: Optional[datetime] = None) -> dict:
    """Executa o detector. apply=False (default) = log-only. Retorna contadores."""
    neurons = scan_neuronios(temporal_root, now=now)
    cold, stale = classify(neurons, days_cold=days_cold, days_stale=days_stale)
    # Boundedness: nunca mexe em mais que `limit` itens por execução.
    budget = cold[:limit]
    stale = stale[: max(0, limit - len(budget))]
    dry = not apply
    for it in budget:
        dest = apply_cold(it, arquivo_root, dry_run=dry)
        logger.info("%s COLD %s → %s", "[dry]" if dry else "[apply]",
                    it["path"].name, dest)
    for it in stale:
        apply_stale(it, dry_run=dry)
        logger.info("%s STALE %s (decision %.0fd)", "[dry]" if dry else "[apply]",
                    it["path"].name, it["age_days"])
    stats = {"scanned": len(neurons), "cold": len(budget), "stale": len(stale),
             "applied": apply}
    logger.info("drift: %s", stats)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Detector de drift (envelhecimento de memória).")
    ap.add_argument("--apply", action="store_true", help="escreve (default: log-only)")
    ap.add_argument("--days-cold", type=int, default=DEFAULT_DAYS_COLD)
    ap.add_argument("--days-stale", type=int, default=DEFAULT_DAYS_STALE)
    ap.add_argument("--limit", type=int, default=MAX_DRIFT_PER_RUN)
    args = ap.parse_args()
    run_drift(days_cold=args.days_cold, days_stale=args.days_stale,
              limit=args.limit, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
