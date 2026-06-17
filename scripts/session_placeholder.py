#!/usr/bin/env python3
"""
Hook SessionStart — cria placeholder do session log.

Lê metadata da sessão (JSON via stdin OU env vars) e cria um arquivo
`cerebro/cerebelo/sessoes/YYYY/MM/DD/HHMM-{session_id}.md` a partir do template
`cerebro/tronco/modelos/session-log.md`. Substitui placeholders `{{date}}`,
`{{session_id}}`, `{{title}}`, `{{project}}` com valores reais.

Idempotente: se o arquivo já existe, não sobrescreve (preserva o que o
`session_update.py` já escreveu). Suporta `dry_run=1` para preview sem I/O.

Stdout: nenhum (hook silencioso). Stderr: erros de I/O.
Exit 0 sempre (não bloqueia o startup do Claude Code).
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Bootstrap paths
_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent))
sys.path.append(SINAPSE_HOME)

from core import paths as cp  # noqa: E402

# Template path: env var override (usado por testes) > paths padrão
TEMPLATE_PATH = Path(os.environ.get("SESSION_TEMPLATE_PATH", str(cp.MODELOS_ROOT / "session-log.md")))


def _read_hook_payload() -> dict:
    """Lê metadata da sessão do stdin (Claude Code envia JSON) ou env vars."""
    # 1. Tenta stdin
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                return json.loads(raw)
        except (json.JSONDecodeError, OSError):
            pass
    # 2. Fallback: env vars convencionais do Claude Code
    return {
        "session_id": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
        "project": os.environ.get("CLAUDE_PROJECT_DIR", SINAPSE_HOME),
        "cwd": os.environ.get("CLAUDE_CWD", SINAPSE_HOME),
    }


def _render_template(template: str, ctx: dict) -> str:
    """Substitui `{{key}}` e `{{key:default com espaços}}` por valores do ctx.

    A regex tolera espaços e qualquer caractere entre `{{` e `}}` (exceto `}`).
    Placeholder desconhecido permanece literal (não falha)."""
    def repl(match: re.Match) -> str:
        inner = match.group(1).strip()
        # Se tiver `:`, a parte antes é a key; resto é só documentação humana
        key = inner.split(":", 1)[0].strip()
        if key in ctx and ctx[key] is not None:
            return str(ctx[key])
        return match.group(0)

    return re.sub(r"\{\{([^}]+?)\}\}", repl, template)


def _session_path(session_id: str, when: datetime) -> Path:
    """Mapeia session_id + datetime → cerebro/cerebelo/sessoes/YYYY/MM/DD/HHMM-{id}.md"""
    folder = cp.SESSIONS_ROOT / when.strftime("%Y/%m/%d")
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)[:64] or "unknown"
    return folder / f"{when.strftime('%H%M')}-{safe_id}.md"


def main() -> int:
    dry_run = os.environ.get("DRY_RUN", "0") == "1"
    payload = _read_hook_payload()
    session_id = payload.get("session_id") or "unknown"
    project = os.path.basename(str(payload.get("project") or "Hive-Mind").rstrip("/"))
    now = datetime.now()

    if not TEMPLATE_PATH.exists():
        print(f"[session_placeholder] Template ausente: {TEMPLATE_PATH}", file=sys.stderr)
        return 0  # não bloqueia o SessionStart

    ctx = {
        "date": now.strftime("%Y-%m-%d %H:%M"),
        "session_id": session_id,
        "title": f"sessão {now.strftime('%Y-%m-%d %H:%M')}",
        "project": project,
        "description": f"Sessão iniciada às {now.strftime('%H:%M')} — projeto {project}",
    }
    rendered = _render_template(TEMPLATE_PATH.read_text(encoding="utf-8"), ctx)

    target = _session_path(session_id, now)
    if target.exists():
        # Idempotente: preserva o que session_update.py já escreveu
        if not dry_run:
            print(f"[session_placeholder] já existe, mantido: {target.relative_to(SINAPSE_HOME)}", file=sys.stderr)
        return 0

    if dry_run:
        print(f"[session_placeholder] DRY_RUN: criaria {target.relative_to(SINAPSE_HOME)}", file=sys.stderr)
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"[session_placeholder] criado: {target.relative_to(SINAPSE_HOME)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
