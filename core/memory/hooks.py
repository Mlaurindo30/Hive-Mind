"""
Hooks de leitura e escrita para o Hermes: pre_prompt_build, post_tool_use,
post_session_end, on_session_finalize.

Puro — recebe todos os parâmetros como argumentos. O chamador
(sinapse-memory.py) passa suas próprias variáveis de módulo correntes,
garantindo que monkeypatch.setattr funcione.
"""

import json
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Event stream / classificação de mensagens
# ---------------------------------------------------------------------------

_EVENT_PRIORITY = {
    "datasource": 0,
    "knowledge": 1,
    "plan": 2,
    "observation": 3,
    "message": 4,
    "system": 5,
    "decision": 2,
    "learning": 2,
}


def classify_message(msg: str) -> str:
    """Classifica mensagem do usuário em tipo de evento."""
    msg_lower = msg.lower().strip()
    if not msg_lower:
        return "system"
    if any(w in msg_lower for w in ["busca", "pesquisa", "procura", "encontra", "search", "find"]):
        return "datasource"
    if any(w in msg_lower for w in ["aprendi", "descobri", "notei", "padrão", "pattern", "insight"]):
        return "learning"
    if any(w in msg_lower for w in ["decidi", "vamos", "quero", "faz", "cria", "implementa"]):
        return "decision"
    if any(w in msg_lower for w in ["planeja", "plano", "como faria", "estratégia"]):
        return "plan"
    return "message"


def generate_plan(msg: str) -> Optional[str]:
    """Gera pseudocódigo numerado estilo Manus Planner."""
    if not msg or not msg.strip():
        return None
    msg_lower = msg.lower()
    steps: List[str] = []

    if any(w in msg_lower for w in ["busca", "pesquisa", "procura", "search"]):
        steps.extend([
            "1. Consultar vault (graphify + sqlite-vec + neural-memory)",
            "2. Se necessário, web_search para informações externas",
            "3. Sintetizar resultados",
        ])

    if any(w in msg_lower for w in ["cria", "criar", "implementa", "faz", "código"]):
        steps.extend([
            "1. Analisar requisitos",
            "2. Consultar vault por padrões e decisões similares",
            "3. Implementar seguindo Boil the Lake",
            "4. Verificar (testar/lint)",
            "5. Registrar decisão no vault",
        ])

    if any(w in msg_lower for w in ["corrige", "debug", "quebrado", "erro", "bug"]):
        steps.extend([
            "1. No Fixes Without Root Cause — investigar antes",
            "2. Reproduzir o erro consistentemente",
            "3. Identificar causa raiz",
            "4. Aplicar correção",
            "5. Verificar que o erro não volta",
        ])

    if any(w in msg_lower for w in ["analisa", "avalia", "review", "veredito"]):
        steps.extend([
            "1. Extrair informações completas",
            "2. Aplicar template Analise Fria",
            "3. Gerar PDF se aplicável",
            "4. Registrar aprendizado no vault",
        ])

    return "\n".join(steps) if steps else None


def format_context(ctx: Dict[str, Any], max_context_chars: int) -> str:
    """Formata contexto do vault para injeção no prompt (conciso)."""
    source = ctx.get("source", "sinapse")
    lines = [f"[Sinapse — {source}]"]

    for obs in ctx.get("observations", []):
        title = obs.get("title", "")
        content = obs.get("content", "")
        if title:
            lines.append(f"  • {title}")
        if content:
            lines.append(f"    {content[:200]}")

    for n in ctx.get("nodes", []):
        src = n.get("source", "")
        line = f"  • {n['label']} ({n['type']})"
        if src:
            line += f" — {src}"
        lines.append(line)
    for e in ctx.get("edges", []):
        lines.append(f"  ↳ {e['source']} → {e['target']} ({e['relation']})")

    result = "\n".join(lines)
    return result[:max_context_chars] + ("\n[...]" if len(result) > max_context_chars else "")


# ---------------------------------------------------------------------------
# Hook: pre_prompt_build
# ---------------------------------------------------------------------------


def pre_prompt_build(
    user_message: str,
    system_message: str,
    query_fn: Callable,
    max_context_chars: int,
    log_fn: Optional[Callable] = None,
    **_kwargs: Any,
) -> Dict[str, Any]:
    """
    Busca contexto relevante em todos os backends e injeta no prompt.

    Args:
        user_message: mensagem do usuário.
        system_message: system prompt atual.
        query_fn: callable(query) → Optional[dict] (query_vault_knowledge).
        max_context_chars: limite de chars para injeção.
        log_fn: callable para logging.
    """
    result: Dict[str, Any] = {}

    if not user_message or not user_message.strip():
        return result

    event_type = classify_message(user_message)
    if log_fn:
        log_fn("info", "pre_prompt_build", event_type=event_type)

    context = query_fn(user_message)
    block = ""

    plan = generate_plan(user_message)
    if plan:
        block = f"[Planner — {event_type}]\n{plan}\n"

    if context:
        vault_block = format_context(context, max_context_chars)
        block = f"{block}\n---\n\n{vault_block}" if block else vault_block

    if block:
        system_message = f"{block}\n\n---\n\n{system_message}" if system_message else block
        result["system_message"] = system_message

    return result


# ---------------------------------------------------------------------------
# Hook: post_tool_use
# ---------------------------------------------------------------------------


def post_tool_use(
    tool_name: str,
    tool_args: Optional[Dict[str, Any]],
    decision_tools: set,
    learning_signals: List[str],
    save_decision_fn: Callable,
    save_learning_fn: Callable,
    session_decisions: List[str],
    session_learnings: List[str],
    **_kwargs: Any,
) -> None:
    """
    Hook chamado após cada tool use.
    Detecta decisões e aprendizados e os espelha no vault.

    Args:
        tool_name: nome da tool chamada.
        tool_args: argumentos da tool.
        decision_tools: set de nomes de tools que disparam save_decision.
        learning_signals: sinais textuais para detectar aprendizados.
        save_decision_fn: callable(title, content) → Optional[str].
        save_learning_fn: callable(title, content) → Optional[str].
        session_decisions: lista mutável acumulada na sessão.
        session_learnings: lista mutável acumulada na sessão.
    """
    if tool_name not in decision_tools:
        return

    if not isinstance(tool_args, dict):
        return

    content = tool_args.get("content") or tool_args.get("narrative") or ""
    if not content:
        return

    title = tool_args.get("title") or content[:80]

    decision_path = save_decision_fn(title, content)
    if decision_path:
        session_decisions.append(decision_path)

    content_lower = content.lower()
    if any(signal in content_lower for signal in learning_signals):
        learning_path = save_learning_fn(title, content)
        if learning_path:
            session_learnings.append(learning_path)


# ---------------------------------------------------------------------------
# Hook: post_session_end
# ---------------------------------------------------------------------------


def post_session_end(
    session_summary: str,
    session_decisions: List[str],
    session_learnings: List[str],
    update_state_fn: Callable,
    **_kwargs: Any,
) -> None:
    """
    Hook chamado ao final da sessão. Atualiza current-state.md.
    """
    if not session_summary:
        return

    update_state_fn(
        decisions=session_decisions,
        learnings=session_learnings,
        summary=session_summary,
    )

    session_decisions.clear()
    session_learnings.clear()


# ---------------------------------------------------------------------------
# Hook: on_session_finalize
# ---------------------------------------------------------------------------


def on_session_finalize(
    session_id: str,
    platform: str,
    vault_dir: str,
    session_decisions: List[str],
    session_learnings: List[str],
    log_fn: Optional[Callable] = None,
    **_kwargs: Any,
) -> None:
    """
    Hook chamado antes do reset de sessão (/new, timeout).
    Equivalente ao PreCompact do Claude Code: faz backup do estado atual.
    """
    if not session_id:
        return

    if log_fn:
        log_fn("info", "pre_compact", session_id=session_id, platform=platform)

    try:
        backup_dir = os.path.join(vault_dir, "thinking", "session-logs")
        os.makedirs(backup_dir, exist_ok=True)
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot = {
            "session_id": session_id,
            "platform": platform,
            "timestamp": datetime.now().isoformat(),
            "decisions": list(session_decisions),
            "learnings": list(session_learnings),
        }
        path = os.path.join(backup_dir, f"session_finalize_{now}.json")
        with open(path, "w") as f:
            json.dump(snapshot, f)

        backups = sorted(
            f for f in os.listdir(backup_dir)
            if f.startswith("session_finalize_") and f.endswith(".json")
        )
        for old in backups[:-10]:
            os.remove(os.path.join(backup_dir, old))

        if log_fn:
            log_fn("info", "pre_compact_saved", path=path, count=len(backups))
    except OSError as e:
        if log_fn:
            log_fn("error", "pre_compact_failed", error=str(e))
