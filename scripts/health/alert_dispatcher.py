#!/usr/bin/env python3
"""
scripts/alert_dispatcher.py — F5.1: despacha alertas de saúde para parietal/inbox/.

Lê o snapshot diário em insula/saude/YYYY-MM-DD.md, extrai cada alerta ativo
da seção '## Alertas', e escreve uma nota por alerta em inbox/YYYY/MM/DD/.
Sem LLM. Idempotente por content-hash. Nova métrica M13 (consumida por health_dashboard).

Uso:
    python scripts/alert_dispatcher.py            # dry-run (só imprime)
    python scripts/alert_dispatcher.py --apply    # escreve arquivos
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import yaml
from datetime import date, datetime
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from core import paths as cp  # noqa: E402

_METRIC_RE = re.compile(r"\b(M\d+)\b")

_SUGGESTED_ACTIONS: dict[str, str] = {
    "M2": "Escrever daily log de hoje em cerebelo/diario/.",
    "M4": "Rodar audit_memory.py --fix-orphans ou revisar MOCs.",
    "M7": "Escrever resumo semanal via weekly_synthesizer.py.",
    "M8": "Revisar decisões estagnadas com decision_promoter.py.",
    "M9": "Verificar dream_cycle.log; ajustar HIVE_MAX_CYCLE_SECONDS se necessário.",
    "M10": "Rodar decision_promoter.py para promover decisões pendentes.",
    "M11": "Rodar pattern_distiller.py para destilar padrões recentes.",
    "M12": "Revisar conflitos em insula/conflitos/ e resolver manualmente.",
}
_DEFAULT_ACTION = "Verificar o dashboard de saúde em insula/saude/."


def load_alerts(saude_root: Path = cp.SAUDE_ROOT, *,
                date: Optional[date] = None) -> list[str]:
    """Extrai lista de strings de alerta do snapshot do dia (seção ## Alertas)."""
    today = date or datetime.now().date()
    snapshot = saude_root / f"{today.isoformat()}.md"
    if not snapshot.exists():
        return []
    text = snapshot.read_text(errors="ignore")
    # Encontra seção ## Alertas
    m = re.search(r"^## Alertas\s*\n(.*?)(?=^##|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        return []
    section = m.group(1)
    alerts = []
    for line in section.splitlines():
        line = line.strip()
        # Só linhas de alerta real (⚠️), ignora ✅
        if line.startswith("- ⚠️ ") or line.startswith("- ⚠"):
            # Remove o prefixo de emoji
            msg = re.sub(r"^- [⚠️\s]+", "", line).strip()
            if msg:
                alerts.append(msg)
    return alerts


def _content_hash8(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def _metric_code(alert: str) -> str:
    m = _METRIC_RE.search(alert)
    return m.group(1) if m else "MX"


def _render_note(alert: str, *, date_str: str) -> str:
    metric = _metric_code(alert)
    action = _SUGGESTED_ACTIONS.get(metric, _DEFAULT_ACTION)
    fm = {
        "type": "health-alert",
        "date": date_str,
        "metric": metric,
        "severity": "warning",
        "message": alert,
        "suggested_action": action,
        "auto_resolved": False,
    }
    return ("---\n" + yaml.dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
            + "---\n\n# Alerta de Saúde: " + metric + "\n\n"
            + alert + "\n\n**Ação sugerida:** " + action + "\n")


def dispatch(alerts: list[str], inbox_root: Path = cp.INBOX_ROOT, *,
             dry_run: bool = True, now: Optional[datetime] = None) -> list[Path]:
    """Escreve 1 nota por alerta em inbox/{YYYY/MM/DD}/alerta-{HHMMSS}-{hash8}.md.
    Idempotente: não reescreve se já existe nota com o mesmo hash de conteúdo."""
    now = now or datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    day_dir = inbox_root / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    written: list[Path] = []

    for alert in alerts:
        note = _render_note(alert, date_str=date_str)
        h8 = _content_hash8(note)
        # Idempotência: busca arquivo existente com o mesmo hash
        if day_dir.exists() and any(day_dir.glob(f"alerta-*-{h8}.md")):
            continue
        fname = f"alerta-{now.strftime('%H%M%S')}-{h8}.md"
        dest = day_dir / fname
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(note, encoding="utf-8")
        written.append(dest)

    return written


def m13_alerts_dispatched_today(inbox_root: Path = cp.INBOX_ROOT, *,
                                now: Optional[datetime] = None) -> int:
    """Conta alertas de saúde já despachados hoje (alerta-*.md com type: health-alert)."""
    now = now or datetime.now()
    day_dir = inbox_root / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    if not day_dir.exists():
        return 0
    count = 0
    for f in day_dir.glob("alerta-*.md"):
        text = f.read_text(errors="ignore")
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1))
            if fm.get("type") == "health-alert":
                count += 1
        except Exception:
            continue
    return count


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Despacha alertas de saúde para parietal/inbox/ (F5.1).")
    ap.add_argument("--apply", action="store_true",
                    help="Escreve arquivos (default: dry-run, só imprime)")
    args = ap.parse_args()
    dry_run = not args.apply

    alerts = load_alerts()
    if not alerts:
        print("[alert_dispatcher] Nenhum alerta ativo hoje.")
        return 0

    written = dispatch(alerts, dry_run=dry_run)
    if dry_run:
        print(f"[alert_dispatcher] DRY-RUN — {len(written)} nota(s) seriam criadas:")
        for p in written:
            print(f"  {p}")
    else:
        print(f"[alert_dispatcher] {len(written)} nota(s) despachada(s):")
        for p in written:
            print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
