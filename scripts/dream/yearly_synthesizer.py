#!/usr/bin/env python3
"""K5 Yearly Synthesizer — writes cerebelo/anual/YYYY.md."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent.parent))
sys.path.append(SINAPSE_HOME)

try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(SINAPSE_HOME) / ".env")
except ImportError:
    pass

from core import paths as cp  # noqa: E402
from core.auth import get_role_config, load_env  # noqa: E402
from core.database import ensure_migrations, get_connection, init_db  # noqa: E402
from core.llm_client import call_llm_with_fallback, classify_llm_error  # noqa: E402
from core.schemas.yearly_models import YearlySummaryModel  # noqa: E402
from core.vector_sync import index_summary_file_to_sqlite  # noqa: E402


YEARLY_PROMPT = """Voce e o yearly_synthesizer do Hive-Mind.
Consolide mensais, marcos e padroes duradouros em memoria historica.
Nao copie os mensais. Promova apenas grandes decisoes, principios, lessons
learned, riscos estrategicos e metas de alto nivel.
Responda APENAS com JSON valido no schema YearlySummaryModel."""


def _collect_monthlies(year: int) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if not cp.MONTHLY_ROOT.exists():
        return entries
    for path in sorted(cp.MONTHLY_ROOT.glob(f"{year:04d}-*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        entries.append({"source_id": str(path), "name": path.stem, "content": text[:6000]})
    return entries


def _collect_db_context(year: int) -> dict[str, Any]:
    init_db()
    conn = get_connection()
    try:
        ensure_migrations(conn)
        decisions = conn.execute(
            """
            SELECT id, label, type, source_file, created_at
            FROM neurons
            WHERE type IN ('decision', 'learning', 'operational_fact')
              AND created_at BETWEEN ? AND ?
            ORDER BY created_at
            LIMIT 100
            """,
            (f"{year:04d}-01-01", f"{year:04d}-12-31T23:59:59"),
        ).fetchall()
        return {"durable_candidates": [dict(row) for row in decisions]}
    finally:
        conn.close()


def _render_list(items: list[str], empty: str = "_Nenhum item duravel identificado._") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def _render_markdown(
    summary: YearlySummaryModel,
    *,
    year: int,
    monthlies: list[dict[str, str]],
    provider: str,
    model: str,
    existing_content: str | None,
) -> str:
    parent_ids = [entry["source_id"] for entry in monthlies]
    generated_at = datetime.now().isoformat()
    output_path = cp.yearly_path(year)
    fm = f"""---
type: yearly-summary
cadence: yearly
year: {year:04d}
period_start: {year:04d}-01-01
period_end: {year:04d}-12-31
source_id: {cp.rel_to_vault(output_path)}
parent_summary_id: {json.dumps(parent_ids, ensure_ascii=False)}
llm_role: yearly_synthesizer
llm_model: {provider}/{model}
generated_at: {generated_at}
status: finalized
generated_by: scripts/dream/yearly_synthesizer.py
---
"""
    body = f"""# Anual {year:04d}

<!-- auto:start -->
## Retrospectiva Histórica
{summary.historical_summary}

## Grandes Decisões
{_render_list(summary.major_decisions)}

## Princípios Duráveis
{_render_list(summary.durable_principles)}

## Lições Aprendidas
{_render_list(summary.learned_lessons)}

## Riscos Estratégicos
{_render_list(summary.strategic_risks)}

## Metas Do Próximo Ano
{_render_list(summary.next_year_goals)}

## Fontes
{_render_list(parent_ids, "_Nenhum mensal encontrado no periodo._")}
<!-- auto:end -->

#yearly #synthesis
"""
    rendered = fm + "\n" + body
    if existing_content and "<!-- auto:start -->" in existing_content:
        auto = re.search(r"<!-- auto:start -->.*?<!-- auto:end -->", rendered, flags=re.DOTALL)
        if auto:
            return re.sub(r"<!-- auto:start -->.*?<!-- auto:end -->", auto.group(0), existing_content, flags=re.DOTALL)
    return rendered


def _index_output(path: Path, cadence: str) -> str:
    init_db()
    conn = get_connection()
    try:
        ensure_migrations(conn)
        return index_summary_file_to_sqlite(conn, path, cadence=cadence)
    finally:
        conn.close()


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--real", action="store_true", help="chama LLM real e indexa summary_vectors")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    year = int(args.year)
    monthlies = _collect_monthlies(year)
    context = {
        "year": year,
        "period_start": f"{year:04d}-01-01",
        "period_end": f"{year:04d}-12-31",
        "monthly_summaries": monthlies,
        **_collect_db_context(year),
    }

    if args.dry_run:
        print(json.dumps({"context": context}, ensure_ascii=False, indent=2)[:4000])
        return 0

    cfg = get_role_config("yearly_synthesizer") or {}
    provider, model = cfg.get("provider"), cfg.get("model")
    if not provider or not model:
        print("[yearly_synthesizer] LLM nao configurado para yearly_synthesizer.", file=sys.stderr)
        return 1
    if not args.real:
        print("[yearly_synthesizer] use --real para gerar sintese anual com LLM real.", file=sys.stderr)
        return 2

    try:
        summary = call_llm_with_fallback(
            "yearly_synthesizer",
            f"CONTEXTO ANUAL:\n{json.dumps(context, ensure_ascii=False, indent=2)}",
            YEARLY_PROMPT,
            YearlySummaryModel,
            max_retries=2,
        )
        output_path = cp.yearly_path(year)
        existing = output_path.read_text(encoding="utf-8") if output_path.exists() else None
        markdown = _render_markdown(
            summary,
            year=year,
            monthlies=monthlies,
            provider=provider,
            model=model,
            existing_content=existing,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        vector_id = _index_output(output_path, "yearly")
        print(f"[yearly_synthesizer] ✓ {output_path.relative_to(SINAPSE_HOME)} summary_vector={vector_id}")
        return 0
    except Exception as exc:
        kind = classify_llm_error(exc)
        print(f"[yearly_synthesizer] falha ({kind}): {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
