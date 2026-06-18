#!/usr/bin/env python3
"""
Weekly Synthesizer — Gera resumo executivo semanal do Hive-Mind (Fase 2 §11).

Disparado por systemd `sinapse-weekly.timer` (Sun 04:00).
Pode também ser rodado manualmente:
    python scripts/weekly_synthesizer.py --year 2026 --week 25
"""

import argparse
import os
import sys
import json
import yaml
import re
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Dict, Any, Optional

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
from core.database import get_connection  # noqa: E402
from core.llm_client import call_llm_with_fallback, classify_llm_error  # noqa: E402
from core.schemas.weekly_models import WeeklySummaryModel, ProjectStatus  # noqa: E402

# Config resolvida sob demanda em main() (NÃO no import — efeito colateral no
# import polui testes de isolamento de env de outros módulos).
LLM_PROVIDER = None
LLM_MODEL = None

PROMPT_PATH = Path(SINAPSE_HOME) / "core/schemas/prompts/weekly_synthesizer_prompt.yaml"

def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        # Fallback simplificado se o arquivo não existir
        return "Gere um resumo semanal estruturado em PT-BR a partir do contexto."
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data["system_prompt"]

WEEKLY_PROMPT = load_prompt()

def get_week_range(year: int, week: int):
    """Retorna o primeiro (segunda) e último (domingo) dia da semana ISO."""
    # datetime.date.fromisocalendar está disponível no Python 3.8+
    start_date = date.fromisocalendar(year, week, 1)
    end_date = date.fromisocalendar(year, week, 7)
    return start_date, end_date

def collect_daily_logs(start_date: date, end_date: date) -> List[Dict[str, Any]]:
    logs = []
    current = start_date
    while current <= end_date:
        path = cp.daily_path(current)
        log_entry = {"date": current.isoformat(), "content": None}
        if path.exists():
            try:
                log_entry["content"] = path.read_text(encoding="utf-8")
            except Exception:
                pass
        logs.append(log_entry)
        current += timedelta(days=1)
    return logs

def collect_sessions(start_date: date, end_date: date) -> List[Dict[str, Any]]:
    sessions = []
    # Busca nas pastas YYYY/MM correspondentes ao range
    # Para simplificar, buscamos em todas as pastas de sessões que podem conter o range
    relevant_months = set()
    current = start_date
    while current <= end_date:
        relevant_months.add((current.year, current.month))
        current += timedelta(days=1)
    
    for year, month in relevant_months:
        month_dir = cp.SESSIONS_ROOT / f"{year}/{month:02d}"
        if month_dir.exists():
            for day_dir in month_dir.iterdir():
                if not day_dir.is_dir(): continue
                try:
                    d = date(year, month, int(day_dir.name))
                    if start_date <= d <= end_date:
                        for session_file in day_dir.glob("*.md"):
                            sessions.append({"name": session_file.name, "path": str(session_file)})
                except ValueError:
                    continue
    return sessions

def query_week_data(start_date: date, end_date: date) -> Dict[str, Any]:
    conn = get_connection()
    try:
        # Átomos (fatos) criados na semana
        atoms = conn.execute("""
            SELECT label, type, created_at, metadata 
            FROM neurons 
            WHERE type='fact' 
            AND created_at BETWEEN ? AND ?
        """, (start_date.isoformat(), end_date.isoformat() + "T23:59:59")).fetchall()
        
        # Decisões na semana
        decisions = conn.execute("""
            SELECT label, metadata, created_at 
            FROM neurons 
            WHERE type='decision' 
            AND created_at BETWEEN ? AND ?
        """, (start_date.isoformat(), end_date.isoformat() + "T23:59:59")).fetchall()
        
        return {
            "atoms": [dict(a) for a in atoms],
            "decisions": [dict(d) for d in decisions]
        }
    finally:
        conn.close()

def collect_projects() -> List[Dict[str, Any]]:
    projects = []
    if cp.PROJECTS_ROOT.exists():
        for p_file in cp.PROJECTS_ROOT.glob("*.md"):
            try:
                content = p_file.read_text(encoding="utf-8")
                # Tenta extrair status do frontmatter simplificado
                status = "unknown"
                if "status: active" in content: status = "active"
                elif "status: blocked" in content: status = "blocked"
                elif "status: completed" in content: status = "completed"
                
                projects.append({
                    "name": p_file.stem,
                    "status": status,
                    "file": str(p_file)
                })
            except Exception:
                continue
    return projects

def _health_section() -> str:
    """Monta '## Métricas de Saúde' (M1-M9 + decisões stale). Não-fatal."""
    try:
        from core.database import get_connection, ensure_migrations
        from scripts.health_dashboard import compute_metrics, render_snapshot, evaluate_alerts
        from scripts.decision_staleness import stale_decisions, render_markdown
        from datetime import datetime as _dt
        conn = get_connection()
        ensure_migrations(conn)
        try:
            m = compute_metrics(conn)
        finally:
            conn.close()
        alerts = evaluate_alerts(m)
        snap = render_snapshot(m, alerts, now=_dt.now())
        # Extrai a tabela + alertas do snapshot (descarta frontmatter/título dele).
        body = snap.split("## Métricas", 1)[1].lstrip("\n")
        stale_md = render_markdown(stale_decisions())
        return ("## Métricas de Saúde\n" + body
                + "\n## Decisões Estagnadas\n" + stale_md)
    except Exception as e:  # nunca derruba o weekly
        return f"## Métricas de Saúde\n_(indisponível: {e})_\n"


def generate_markdown(summary: WeeklySummaryModel, year: int, week: int, start_date: date, end_date: date, daily_logs: List[Dict[str, Any]], existing_content: Optional[str] = None) -> str:
    # Geramos o bloco de conteúdo automático
    auto_content = f"""
## Visão Geral
{summary.overview}

## Daily Compliance
| Dia | Status |
|---|---|
"""
    for log in daily_logs:
        status = "✅" if log["content"] else "❌"
        auto_content += f"| {log['date']} | {status} |\n"
    
    auto_content += "\n## Top 5 Átomos\n"
    for atom in summary.top_atoms:
        auto_content += f"- {atom}\n"
    
    auto_content += "\n## Decisões\n"
    if summary.decisions_closed:
        auto_content += "### Fechadas\n"
        for d in summary.decisions_closed:
            auto_content += f"- {d}\n"
    
    if summary.decisions_open:
        auto_content += "\n### Abertas/Em Discussão\n"
        for d in summary.decisions_open:
            auto_content += f"- {d}\n"
            
    auto_content += "\n## Projetos: Status\n"
    auto_content += "| Projeto | Status | Blockers | Delta |\n"
    auto_content += "|---|---|---|---|\n"
    for p in summary.projects:
        auto_content += f"| {p.name} | {p.status} | {p.blockers} | {p.delta} |\n"
        
    auto_content += "\n## Padrões Emergentes\n"
    for pattern in summary.patterns:
        auto_content += f"- {pattern}\n"
        
    auto_content += "\n## Próxima Semana\n"
    for priority in summary.next_week_priorities:
        auto_content += f"- {priority}\n"

    # --- Métricas de Saúde (F3.4): reusa health_dashboard + decision_staleness ---
    # Não duplica lógica; falha aqui é não-fatal (o weekly não pode quebrar por isso).
    auto_content += "\n" + _health_section()

    # Envolvemos em marcadores de automação
    wrapped_auto = f"<!-- auto:start -->\n{auto_content.strip()}\n<!-- auto:end -->"
    
    if existing_content:
        # Tenta substituir o bloco existente
        pattern = r"<!-- auto:start -->.*?<!-- auto:end -->"
        if "<!-- auto:start -->" in existing_content:
            return re.sub(pattern, wrapped_auto, existing_content, flags=re.DOTALL)
        
        # Se não há marcadores mas o arquivo existe, preservamos o conteúdo original
        # e inserimos o novo conteúdo após o frontmatter ou no início.
        fm_match = re.match(r"^---\s*\n.*?\n---\s*\n", existing_content, re.DOTALL)
        if fm_match:
            header = fm_match.group(0)
            body = existing_content[len(header):]
            return header + "\n" + wrapped_auto + "\n" + body
        else:
            return wrapped_auto + "\n\n" + existing_content

    # Se for um arquivo novo
    fm = f"""---
type: weekly-summary
week: {year}-W{week:02d}
start_date: {start_date.isoformat()}
end_date: {end_date.isoformat()}
generated_at: {datetime.now().isoformat()}
status: finalized
generated_by: scripts/weekly_synthesizer.py
---
"""
    header = f"# Semana {year}-W{week:02d} ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')})\n"
    footer = "\n\n#weekly #synthesis"
    
    return fm + "\n" + header + "\n" + wrapped_auto + footer

def main():
    global LLM_PROVIDER, LLM_MODEL
    load_env()  # carrega env só na execução (não no import)
    _cfg = get_role_config("weekly_synthesizer") or {}
    LLM_PROVIDER = _cfg.get("provider")
    LLM_MODEL = _cfg.get("model")

    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=date.today().isocalendar()[0])
    parser.add_argument("--week", type=int, default=date.today().isocalendar()[1] - 1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Ajuste para virada de ano se a semana for 0
    year, week = args.year, args.week
    if week <= 0:
        year -= 1
        week = 52 # Aproximação simplificada

    start_date, end_date = get_week_range(year, week)
    print(f"[weekly_synthesizer] Gerando síntese para {year}-W{week:02d} ({start_date} até {end_date})...")

    daily_logs = collect_daily_logs(start_date, end_date)
    sessions = collect_sessions(start_date, end_date)
    db_data = query_week_data(start_date, end_date)
    projects = collect_projects()

    context = {
        "week": f"{year}-W{week:02d}",
        "daily_logs_count": len([l for l in daily_logs if l["content"]]),
        "daily_logs_summaries": [l["content"][:1000] for l in daily_logs if l["content"]],
        "atoms": db_data["atoms"],
        "decisions": db_data["decisions"],
        "sessions_count": len(sessions),
        "projects_active": projects
    }

    if args.dry_run:
        print("[DRY RUN] Contexto coletado com sucesso.")
        # print(json.dumps(context, indent=2))
        return 0

    if not LLM_PROVIDER or not LLM_MODEL:
        print("[ERROR] LLM não configurado para 'weekly_synthesizer'. Verifique seu .env.", file=sys.stderr)
        return 1

    try:
        output_path = cp.weekly_path(year, week)
        existing_content = None
        if output_path.exists():
            existing_content = output_path.read_text(encoding="utf-8")

        summary = call_llm_with_fallback(
            "weekly_synthesizer",
            f"CONTEXTO DA SEMANA:\n{json.dumps(context, indent=2)}",
            WEEKLY_PROMPT,
            WeeklySummaryModel
        )
        
        md_content = generate_markdown(summary, year, week, start_date, end_date, daily_logs, existing_content)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_content, encoding="utf-8")
        
        print(f"[SUCCESS] Síntese semanal gravada em: {output_path.relative_to(SINAPSE_HOME)}")
        return 0
    except Exception as e:
        kind = classify_llm_error(e)
        print(f"[ERROR] Falha na síntese LLM ({kind}): {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
