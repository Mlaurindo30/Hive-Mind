#!/usr/bin/env python3
"""
Daily Writer — agrega sessões do dia em um daily log (Fase 1 §11).

Disparado por systemd `sinapse-daily.timer` (OnCalendar=*-*-* 23:55:00).
Pode também ser rodado manualmente para preview/backfill:
    python scripts/daily_writer.py --date 2026-06-17
    python scripts/daily_writer.py --date 2026-06-17 --dry-run

Lê todos os session logs de `cerebro/cerebelo/sessoes/YYYY/MM/DD/` (consolidados
ou não) e gera `cerebro/cerebelo/diario/YYYY/MM/YYYY-MM-DD.md` com:
  - Frontmatter a partir do template `daily-log.md`
  - ## Sessões do dia (lista de links p/ cada session log)
  - ## Highlights + ## Aprendizados (gerados por LLM, papel `daily_writer`)

Idempotente: roda 2x no mesmo dia, SOBRESCREVE o daily anterior. Sessões
consolidadas aparecem com badge `[consolidated]`; não-consolidadas com
`[pending]` para flag visual.

Exit codes:
  0 = sucesso (incluindo dry-run)
  1 = erro de I/O ou LLM (mas daily é gerado mesmo com erro — LLM falha
      não-bloqueante, deixa placeholders)
"""

import argparse
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent))
sys.path.append(SINAPSE_HOME)

# Carrega .env cedo
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(SINAPSE_HOME) / ".env")
except ImportError:
    pass

from core import paths as cp  # noqa: E402
from core.auth import get_role_config, load_env  # noqa: E402
from core.llm_client import call_llm_with_fallback, classify_llm_error  # noqa: E402
from core.schemas.session_models import DailySummary  # noqa: E402

load_env()

# Override para testes: redireciona SESSIONS_ROOT e DAILY_ROOT para tmp_path
_TEST_SESSIONS_ROOT = os.environ.get("SESSIONS_ROOT_OVERRIDE")
_TEST_DAILY_ROOT = os.environ.get("DAILY_ROOT_OVERRIDE")
_TEST_TEMPLATE_PATH = os.environ.get("DAILY_TEMPLATE_PATH")

if _TEST_SESSIONS_ROOT:
    cp.SESSIONS_ROOT = Path(_TEST_SESSIONS_ROOT)  # type: ignore[attr-defined]
if _TEST_DAILY_ROOT:
    cp.DAILY_ROOT = Path(_TEST_DAILY_ROOT)  # type: ignore[attr-defined]

_cfg = get_role_config("daily_writer") or {}
LLM_PROVIDER = _cfg.get("provider")
LLM_MODEL = _cfg.get("model")

DAILY_PROMPT = """Você é o daily writer do Hive-Mind (cérebro digital do Michel).
Dado um conjunto de session logs de um dia, gere um resumo executivo estruturado
com 3-5 highlights (conquistas/decisões relevantes — foco no que AVANÇOU) e
3-5 aprendizados (padrões, insights, lessons learned — conectar observações em
abstração reutilizável).

Responda APENAS com JSON que casa DailySummary (highlights, learnings).
Se as sessões estiverem vazias ou sem substância, retorne arrays vazios."""


def _collect_sessions(day: date) -> list[Path]:
    """Coleta todos os session logs do dia, ordenados por hora."""
    folder = cp.SESSIONS_ROOT / day.strftime("%Y/%m/%d")
    if not folder.exists():
        return []
    return sorted(folder.glob("*.md"))


def _session_label(path: Path) -> str:
    """Extrai frontmatter `description` e `session_id` para o link do daily."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return path.stem
    desc = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
    sid = re.search(r"^session_id:\s*(.+)$", text, re.MULTILINE)
    consolidated = bool(re.search(r"^consolidated:\s*true", text, re.MULTILINE | re.IGNORECASE))
    badge = "✓" if consolidated else "⏳"
    desc_short = (desc.group(1).strip() if desc else path.stem)[:80]
    sid_short = sid.group(1).strip() if sid else "?"
    return f"- {badge} [[{path.stem}|{path.stem}]] — {desc_short} _(session_id: {sid_short})_"


def _render_sessions_section(sessions: list[Path]) -> str:
    if not sessions:
        return "_Nenhuma sessão registrada hoje._"
    return "\n".join(_session_label(s) for s in sessions)


def _extract_aggregate_transcript(sessions: list[Path], max_chars: int = 20000) -> str:
    """Cola os transcripts dos sessions logs (limitado)."""
    parts = []
    for s in sessions:
        try:
            text = s.read_text(encoding="utf-8")
            # Remove frontmatter
            text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
            parts.append(f"=== {s.stem} ===\n{text}\n")
        except OSError:
            continue
    blob = "\n".join(parts)
    if len(blob) > max_chars:
        blob = blob[:max_chars] + f"\n\n[... truncado em {max_chars} chars ...]"
    return blob


def _render_template(template: str, ctx: dict) -> str:
    def repl(match: re.Match) -> str:
        inner = match.group(1).strip()
        key = inner.split(":", 1)[0].strip()
        return str(ctx.get(key, match.group(0)))
    return re.sub(r"\{\{([^}]+?)\}\}", repl, template)


def _call_llm_highlights(aggregate: str) -> str:
    """Retorna markdown pronto para colar nas seções Highlights + Aprendizados."""
    if not aggregate.strip():
        return ""
    if not LLM_PROVIDER or not LLM_MODEL:
        return "_LLM não configurado para o papel `daily_writer` — preencha manualmente._"
    try:
        prompt = f"SESSÕES CONSOLIDADAS DO DIA:\n```\n{aggregate}\n```\n\nGere o JSON do DailySummary."
        summary = call_llm_with_fallback(
            "daily_writer",
            prompt,
            DAILY_PROMPT,
            DailySummary,
        )
        parts = []
        if summary.highlights:
            parts.append("### Highlights")
            for h in summary.highlights:
                parts.append(f"- {h}")
        if summary.learnings:
            parts.append("\n### Aprendizados")
            for l in summary.learnings:
                parts.append(f"- {l}")
        return "\n".join(parts)
    except Exception as e:
        kind = classify_llm_error(e)
        return f"_⚠️ LLM falhou ({kind}: {e}) — preencha Highlights/Aprendizados manualmente._"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD (default: hoje)")
    parser.add_argument("--dry-run", action="store_true", help="não escreve nem chama LLM")
    parser.add_argument("--no-llm", action="store_true", help="pula LLM, só monta o esqueleto")
    args = parser.parse_args()

    dry_run = args.dry_run or os.environ.get("DRY_RUN", "0") == "1"
    target_day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    sessions = _collect_sessions(target_day)

    if not sessions and not dry_run:
        print(f"[daily_writer] Nenhuma sessão em {target_day.isoformat()} — daily não gerado.")
        return 0

    template_path = Path(os.environ.get("DAILY_TEMPLATE_PATH", str(cp.MODELOS_ROOT / "daily-log.md")))
    if not template_path.exists():
        print(f"[daily_writer] Template ausente: {template_path}", file=sys.stderr)
        return 1

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ctx = {
        "date": target_day.isoformat(),
        "description": (
            f"Daily log de {target_day.isoformat()} — "
            f"{len(sessions)} sessão(ões) registrada(s)"
        ),
        "project": "Hive-Mind",
        "created": now,
        "updated": now,
    }
    rendered = _render_template(template_path.read_text(encoding="utf-8"), ctx)

    # Injeta as seções dinâmicas
    sessions_md = _render_sessions_section(sessions)
    aggregate = "" if (dry_run or args.no_llm) else _extract_aggregate_transcript(sessions)
    highlights_md = (
        "_DRY_RUN: LLM não chamado._" if dry_run
        else (_call_llm_highlights(aggregate) if not args.no_llm else "_LLM pulado (--no-llm)._")
    )

    rendered = rendered.replace(
        "## Sessões do dia\n<!--",
        f"## Sessões do dia\n{sessions_md}\n\n<!--",
    )
    rendered = rendered.replace(
        "## Highlights\n<!--",
        f"## Highlights\n\n{highlights_md}\n\n<!--",
    )

    target = cp.DAILY_ROOT / target_day.strftime("%Y/%m") / f"{target_day.isoformat()}.md"
    if dry_run:
        print(f"[daily_writer] DRY_RUN: criaria {target.relative_to(SINAPSE_HOME)}")
        print(f"  Sessões encontradas: {len(sessions)}")
        print(f"  Primeiras linhas do conteúdo:\n{rendered[:500]}")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"[daily_writer] ✓ {target.relative_to(SINAPSE_HOME)} ({len(sessions)} sessões)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
