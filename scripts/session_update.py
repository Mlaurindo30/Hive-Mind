#!/usr/bin/env python3
"""
Hook PostToolUse — append incremental ao session log ativo.

Lê evento de tool_use do stdin (Claude Code envia JSON) e faz append de
`- [HH:MM:SS] tool=X` no session log ativo da sessão. O session log é
localizado por varredura: o mais recente arquivo `.md` em
`cerebro/cerebelo/sessoes/YYYY/MM/DD/` cujo filename começa com HHMM.

Throttle: máx 1 append/segundo/sessão (checagem por mtime). Evita flood de
PostToolUse em sessões com muitas tool calls.

Idempotente: se a sessão foi consolidada (arquivo com frontmatter
`consolidated: true` OU seção `## Resumo` preenchida), ignora silenciosamente.

Exit 0 sempre (não bloqueia o PostToolUse do Claude Code).
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent))
sys.path.append(SINAPSE_HOME)

from core import paths as cp  # noqa: E402

# Override para testes: redireciona SESSIONS_ROOT para tmp_path
_TEST_SESSIONS_ROOT = os.environ.get("SESSIONS_ROOT_OVERRIDE")
if _TEST_SESSIONS_ROOT:
    SESSIONS_ROOT = Path(_TEST_SESSIONS_ROOT)
else:
    SESSIONS_ROOT = cp.SESSIONS_ROOT

# Throttle: 1s entre appends
THROTTLE_SECONDS = float(os.environ.get("SESSION_UPDATE_THROTTLE", "1.0"))


def _read_hook_payload() -> dict:
    """Lê evento de tool_use do stdin ou env vars."""
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                return json.loads(raw)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "tool": os.environ.get("CLAUDE_TOOL_NAME", "unknown"),
        "session_id": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
    }


def _find_active_session(when: datetime) -> Path | None:
    """Encontra o session log ativo da sessão atual.

    Estratégia: o mais recente `.md` em `cerebro/cerebelo/sessoes/YYYY/MM/DD/`
    cujo filename começa com HHMM (formato do placeholder). Se múltiplos
    arquivos têm o mesmo HHMM, retorna o mais recente por mtime.
    """
    folder = SESSIONS_ROOT / when.strftime("%Y/%m/%d")
    if not folder.exists():
        return None
    candidates = sorted(
        folder.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _is_consolidated(target: Path) -> bool:
    """Detecta se a sessão já foi consolidada (frontmatter `consolidated: true`
    OU seção `## Resumo` não-vazia)."""
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return False
    if re.search(r"^consolidated:\s*true", text, re.MULTILINE | re.IGNORECASE):
        return True
    # Heurística: seção ## Resumo com conteúdo real (>30 chars) = consolidada.
    # Ignora comentários HTML do placeholder (<!-- ... -->), senão o placeholder
    # vazio é falso-positivo e o session_update nunca faz append.
    m = re.search(r"^## Resumo\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if m:
        body = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.DOTALL).strip()
        if len(body) > 30:
            return True
    return False


def _throttled(target: Path) -> bool:
    """Retorna True se o último append foi há menos de THROTTLE_SECONDS."""
    try:
        last = target.stat().st_mtime
    except OSError:
        return False
    return (time.time() - last) < THROTTLE_SECONDS


def _format_action(payload: dict, when: datetime) -> str:
    tool = payload.get("tool", "?")
    args = payload.get("args") or payload.get("input_summary") or ""
    result = payload.get("result") or payload.get("output_summary") or ""
    args_short = str(args)[:80].replace("\n", " ")
    result_short = str(result)[:80].replace("\n", " ")
    return f"- [{when.strftime('%H:%M:%S')}] tool={tool} args={args_short} result={result_short}"


def main() -> int:
    dry_run = os.environ.get("DRY_RUN", "0") == "1"
    payload = _read_hook_payload()
    now = datetime.now()

    target = _find_active_session(now)
    if target is None:
        # Sem session log ativo. Não é erro: o SessionStart pode ter rodado
        # em outra máquina ou antes do CLAUDE_SESSION_ID ser setado.
        if os.environ.get("DEBUG_HOOKS") == "1":
            print(f"[session_update] nenhum session log ativo em {SESSIONS_ROOT}", file=sys.stderr)
        return 0

    if _is_consolidated(target):
        # Sessão já fechada pelo consolidator. Ignora.
        return 0

    if _throttled(target):
        # Throttle: pula este evento silenciosamente.
        return 0

    action = _format_action(payload, now) + "\n"
    if dry_run:
        print(f"[session_update] DRY_RUN: append em {target.relative_to(SINAPSE_HOME)}: {action.strip()}", file=sys.stderr)
        return 0

    # Append logo após a seção "## Ações" (criada pelo template).
    # Se a seção não existe (placeholder pré-template), append no fim.
    text = target.read_text(encoding="utf-8")
    if "## Ações" in text:
        # Insere após o cabeçalho da seção
        text = re.sub(
            r"(## Ações\n)",
            r"\1\n" + action,
            text,
            count=1,
        )
    else:
        text += f"\n## Ações\n\n{action}"

    target.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
