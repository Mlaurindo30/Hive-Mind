#!/usr/bin/env python3
"""K5 Monthly Synthesizer — writes cerebelo/mensal/YYYY-MM.md."""
from __future__ import annotations

import argparse
import calendar
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
from core.schemas.monthly_models import MonthlySummaryModel  # noqa: E402
from core.vector_sync import index_summary_file_to_sqlite  # noqa: E402


MONTHLY_PROMPT = """Voce e o monthly_synthesizer do Hive-Mind.
Consolide semanais, decisoes e sinais de saude em uma sintese mensal.
Nao copie texto bruto. Promova apenas decisoes duraveis, aprendizados
reutilizaveis, riscos persistentes e metas acionaveis.
Responda APENAS com JSON valido no schema MonthlySummaryModel."""


def _parse_month(value: str) -> tuple[int, int]:
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise argparse.ArgumentTypeError("--month deve estar no formato YYYY-MM")
    year, month = map(int, value.split("-"))
    if not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("mes invalido")
    return year, month


def _month_range(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _collect_weeklies(start: date, end: date) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if not cp.WEEKLY_ROOT.exists():
        return entries
    for path in sorted(cp.WEEKLY_ROOT.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _overlaps_period(text, start, end):
            entries.append({"source_id": str(path), "name": path.stem, "content": text[:5000]})
    return entries


def _overlaps_period(text: str, start: date, end: date) -> bool:
    dates = []
    for key in ("start_date", "end_date"):
        match = re.search(rf"^{key}:\s*([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}})", text, re.MULTILINE)
        if match:
            try:
                dates.append(datetime.strptime(match.group(1), "%Y-%m-%d").date())
            except ValueError:
                pass
    if len(dates) == 2:
        return dates[0] <= end and dates[1] >= start
    return True


def _collect_db_context(start: date, end: date) -> dict[str, Any]:
    init_db()
    conn = get_connection()
    try:
        ensure_migrations(conn)
        until = end.isoformat() + "T23:59:59"
        decisions = conn.execute(
            """
            SELECT id, label, type, source_file, created_at
            FROM neurons
            WHERE type IN ('decision', 'learning', 'operational_fact')
              AND created_at BETWEEN ? AND ?
            ORDER BY created_at
            LIMIT 50
            """,
            (start.isoformat(), until),
        ).fetchall()
        return {"durable_candidates": [dict(row) for row in decisions]}
    finally:
        conn.close()


def _render_list(items: list[str], empty: str = "_Nenhum item duravel identificado._") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def _render_markdown(
    summary: MonthlySummaryModel,
    *,
    year: int,
    month: int,
    start: date,
    end: date,
    weeklies: list[dict[str, str]],
    provider: str,
    model: str,
    existing_content: str | None,
) -> str:
    month_id = f"{year:04d}-{month:02d}"
    parent_ids = [entry["source_id"] for entry in weeklies]
    generated_at = datetime.now().isoformat()
    fm = f"""---
type: monthly-summary
cadence: monthly
month: {month_id}
period_start: {start.isoformat()}
period_end: {end.isoformat()}
source_id: {cp.rel_to_vault(cp.monthly_path(year, month))}
parent_summary_id: {json.dumps(parent_ids, ensure_ascii=False)}
llm_role: monthly_synthesizer
llm_model: {provider}/{model}
generated_at: {generated_at}
status: finalized
generated_by: scripts/dream/monthly_synthesizer.py
---
"""
    body = f"""# Mensal {month_id}

<!-- auto:start -->
## Sintese Executiva
{summary.executive_summary}

## Decisões Duráveis
{_render_list(summary.durable_decisions)}

## Aprendizados Duráveis
{_render_list(summary.durable_learnings)}

## Riscos Persistentes
{_render_list(summary.persistent_risks)}

## Metas
{_render_list(summary.goals)}

## Drift Estratégico
{_render_list(summary.strategy_drift)}

## Fontes
{_render_list(parent_ids, "_Nenhum semanal encontrado no periodo._")}
<!-- auto:end -->

#monthly #synthesis
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
    parser.add_argument("--month", default=date.today().strftime("%Y-%m"), help="YYYY-MM")
    parser.add_argument("--real", action="store_true", help="chama LLM real e indexa summary_vectors")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        year, month = _parse_month(args.month)
    except argparse.ArgumentTypeError as exc:
        print(f"[monthly_synthesizer] {exc}", file=sys.stderr)
        return 2

    start, end = _month_range(year, month)
    weeklies = _collect_weeklies(start, end)
    db_context = _collect_db_context(start, end)
    context = {
        "month": f"{year:04d}-{month:02d}",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "weekly_summaries": weeklies,
        **db_context,
    }

    if args.dry_run:
        print(json.dumps({"context": context}, ensure_ascii=False, indent=2)[:4000])
        return 0

    cfg = get_role_config("monthly_synthesizer") or {}
    provider, model = cfg.get("provider"), cfg.get("model")
    if not provider or not model:
        print("[monthly_synthesizer] LLM nao configurado para monthly_synthesizer.", file=sys.stderr)
        return 1
    if not args.real:
        print("[monthly_synthesizer] use --real para gerar sintese mensal com LLM real.", file=sys.stderr)
        return 2

    try:
        summary = call_llm_with_fallback(
            "monthly_synthesizer",
            f"CONTEXTO MENSAL:\n{json.dumps(context, ensure_ascii=False, indent=2)}",
            MONTHLY_PROMPT,
            MonthlySummaryModel,
            max_retries=2,
        )
        output_path = cp.monthly_path(year, month)
        existing = output_path.read_text(encoding="utf-8") if output_path.exists() else None
        markdown = _render_markdown(
            summary,
            year=year,
            month=month,
            start=start,
            end=end,
            weeklies=weeklies,
            provider=provider,
            model=model,
            existing_content=existing,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        vector_id = _index_output(output_path, "monthly")
        print(f"[monthly_synthesizer] ✓ {output_path.relative_to(SINAPSE_HOME)} summary_vector={vector_id}")
        return 0
    except Exception as exc:
        kind = classify_llm_error(exc)
        print(f"[monthly_synthesizer] falha ({kind}): {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
