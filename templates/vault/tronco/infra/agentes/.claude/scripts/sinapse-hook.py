#!/usr/bin/env python3
"""
Sinapse Agent — Claude Code/Codex Hook Script
Chamado pelos hooks SessionStart e Stop para integrar memória automaticamente.

Uso:
  python3 .claude/scripts/sinapse-hook.py session-start
  python3 .claude/scripts/sinapse-hook.py session-end
  python3 .claude/scripts/sinapse-hook.py tool-detect

Recebe contexto do hook via stdin (JSON) e variáveis de ambiente.
Faz fallback para SINAPSE_HOME ou detecta a partir do vault path.
"""

import json
import os
import select
import sys
from pathlib import Path

# Resolve SINAPSE_HOME
sinapse_home = os.environ.get("SINAPSE_HOME")
if not sinapse_home:
    # Detecta: vault está em cerebro/, SINAPSE_HOME é o diretório pai
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("CODEX_PROJECT_DIR") or os.getcwd()
    vault_root = Path(cwd)
    # Se estamos dentro de cerebro/, sobe um nível
    if vault_root.name == "cerebro":
        sinapse_home = str(vault_root.parent)
    elif (vault_root / "cerebro").is_dir():
        sinapse_home = str(vault_root)
    else:
        sinapse_home = os.path.expanduser("~/Documentos/Projects/sinapse_agent")

os.environ["SINAPSE_HOME"] = sinapse_home

# Importa o módulo
sys.path.insert(0, sinapse_home)
import importlib.util
_plugin_path = Path(sinapse_home) / "plugins" / "hermes" / "sinapse-memory.py"
spec = importlib.util.spec_from_file_location("sinapse_memory", _plugin_path)
sm = importlib.util.module_from_spec(spec)
sys.modules["sinapse_memory"] = sm
spec.loader.exec_module(sm)


def _read_stdin_with_timeout(timeout: float = 0.1) -> str:
    """Lê stdin de forma não-bloqueante usando select (evita hangs interativos)."""
    try:
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if r:
            return sys.stdin.read()
    except Exception:
        pass
    return ""


def hook_session_start():
    """Hook SessionStart: busca contexto relevante do vault."""
    # Tenta extrair contexto do hook
    context_text = ""
    try:
        hook_input = json.loads(_read_stdin_with_timeout())
        context_text = hook_input.get("prompt", "") or hook_input.get("user_message", "")
    except (json.JSONDecodeError, ValueError):
        pass

    if not context_text:
        context_text = os.environ.get("CLAUDE_PROMPT", "") or "current session context"

    result = sm._query_vault_knowledge(context_text)
    if result:
        block = sm._format_context(result)
        # Claude Code hooks podem injetar contexto via stdout
        # O hook deve retornar JSON com "systemMessage" ou "additionalContext"
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": block
            }
        }
        print(json.dumps(output, default=str))
    else:
        # Sem resultados, não polui o contexto
        pass


def hook_session_end():
    """Hook Stop/SessionEnd: atualiza Current State."""
    summary = ""
    try:
        hook_input = json.loads(_read_stdin_with_timeout())
        summary = hook_input.get("summary", "") or hook_input.get("session_summary", "")
    except (json.JSONDecodeError, ValueError):
        pass

    if not summary:
        summary = "Session completed — automated hook"

    sm._update_current_state([], [], summary)
    print(json.dumps({"sinapse": "session-end", "updated": True}))


def hook_tool_detect():
    """Hook PostToolUse: detecta memory_add e espelha no vault."""
    try:
        hook_input = json.loads(_read_stdin_with_timeout())
        tool_name = hook_input.get("tool_name", "") or hook_input.get("toolName", "")
        tool_args = hook_input.get("tool_input", {}) or hook_input.get("arguments", {})

        if tool_name in sm.DECISION_TOOLS:
            content = (tool_args.get("content") or tool_args.get("narrative") or "")
            title = tool_args.get("title") or content[:80] if content else ""
            if content and title:
                path = sm._save_decision(title, content)
                print(json.dumps({"sinapse": "decision-saved", "path": path}))
    except (json.JSONDecodeError, ValueError):
        pass


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "session-start"

    if action == "session-start":
        hook_session_start()
    elif action == "session-end":
        hook_session_end()
    elif action == "tool-detect":
        hook_tool_detect()
    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)
