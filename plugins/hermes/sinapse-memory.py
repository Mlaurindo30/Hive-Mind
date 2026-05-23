"""
Sinapse Agent — Plugin de Memória para Hermes
==============================================
Integração bidirecional entre Hermes, Obsidian vault, Graphify e claude-mem.

Fluxo:
  LEITURA (pre_prompt_build):
    1. Mensagem do usuário → extrai entidades
    2. Consulta graph.json (Graphify) por contexto relevante
    3. Injeta no system prompt antes da resposta

  ESCRITA (post_tool_use + post_session_end):
    1. Decisão tomada → salva em cerebro/_decisions/YYYY-MM-DD-titulo.md
    2. Aprendizado → salva em cerebro/_learnings/
    3. Estado atualizado → cerebro/_memory/current-state.md
    4. Notas salvas com frontmatter YAML + WikiLinks

  SYNC (cron trigger):
    1. Graphify reindexa o vault → graph.json atualizado
    2. claude-mem registra observação da decisão

Tudo converge no vault Obsidian como fonte única.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

SINAPSE_HOME = os.path.expanduser("~/Documentos/Projects/sinapse_agent")
VAULT_DIR = os.path.join(SINAPSE_HOME, "cerebro")
GRAPH_JSON = os.path.join(VAULT_DIR, "graphify-out", "graph.json")
DECISIONS_DIR = os.path.join(VAULT_DIR, "_decisions")
LEARNINGS_DIR = os.path.join(VAULT_DIR, "_learnings")
MEMORY_FILE = os.path.join(VAULT_DIR, "_memory", "current-state.md")
PROJECTS_DIR = os.path.join(VAULT_DIR, "_projects")

MAX_CONTEXT_CHARS = 3000
MAX_NODES = 5

# ---------------------------------------------------------------------------
# Registro no Hermes
# ---------------------------------------------------------------------------

def register(ctx):
    """Registra hooks de leitura e escrita no Hermes."""
    ctx.register_hook("pre_prompt_build", _pre_prompt_build)      # leitura
    ctx.register_hook("post_tool_use", _post_tool_use)            # escrita
    ctx.register_hook("post_session_end", _post_session_end)      # escrita final


# ===========================================================================
# LEITURA — injeta contexto do vault no prompt
# ===========================================================================

def _pre_prompt_build(
    user_message: str = "",
    system_message: str = "",
    memory_context: str = "",
    **_kwargs: Any,
) -> Dict[str, Any]:
    """Busca contexto relevante no knowledge graph e injeta no prompt."""
    result: Dict[str, Any] = {}

    if not user_message or not user_message.strip():
        return result

    context = _query_vault_knowledge(user_message)
    if context:
        block = _format_context(context)
        system_message = f"{block}\n\n---\n\n{system_message}" if system_message else block
        result["system_message"] = system_message

    return result


def _query_vault_knowledge(query: str) -> Optional[Dict[str, Any]]:
    """
    Consulta o graph.json por nodes e edges relevantes.
    Busca textual simples — para busca semântica real, usar MCP server.
    """
    if not os.path.isfile(GRAPH_JSON):
        return None

    try:
        with open(GRAPH_JSON, "r") as f:
            graph = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    words = set(query.lower().split())
    matched_nodes = []
    matched_edges = []

    for node in graph.get("nodes", []):
        label = (node.get("label") or "").lower()
        node_type = (node.get("file_type") or "").lower()
        if any(w in label or w in node_type for w in words):
            matched_nodes.append({
                "label": node.get("label"),
                "type": node.get("file_type"),
                "source": node.get("source_file"),
                "community": node.get("community"),
                "score": sum(1 for w in words if w in label),
            })

    matched_nodes.sort(key=lambda n: n["score"], reverse=True)
    matched_nodes = matched_nodes[:MAX_NODES]

    for link in graph.get("links", []):
        source = (link.get("source") or "").lower()
        target = (link.get("target") or "").lower()
        rel = (link.get("relation") or "").lower()
        if any(w in source or w in target or w in rel for w in words):
            matched_edges.append({
                "source": link.get("source"),
                "target": link.get("target"),
                "relation": link.get("relation"),
            })

    if not matched_nodes and not matched_edges:
        return None

    return {"nodes": matched_nodes, "edges": matched_edges[:MAX_NODES], "query": query}


def _format_context(ctx: Dict[str, Any]) -> str:
    """Formata contexto do vault para injeção no prompt (conciso)."""
    lines = ["[Sinapse — Vault Context]"]
    for n in ctx.get("nodes", []):
        src = n.get("source", "")
        line = f"  • {n['label']} ({n['type']})"
        if src:
            line += f" — {src}"
        lines.append(line)
    for e in ctx.get("edges", []):
        lines.append(f"  ↳ {e['source']} → {e['target']} ({e['relation']})")

    result = "\n".join(lines)
    return result[:MAX_CONTEXT_CHARS] + ("\n[...]" if len(result) > MAX_CONTEXT_CHARS else "")


# ===========================================================================
# ESCRITA — salva decisões e aprendizados no vault
# ===========================================================================

# Padrões para detectar quando uma decisão ou aprendizado foi registrado
DECISION_TOOLS = {"memory_add", "observation_add", "mcp_claude_mem_memory_add"}
LEARNING_SIGNALS = ["aprendizado", "learning", "insight", "padrão", "pattern", "lição"]

# Buffer acumulado durante a sessão
_session_decisions: List[str] = []
_session_learnings: List[str] = []


def _post_tool_use(
    tool_name: str = "",
    tool_args: Optional[Dict[str, Any]] = None,
    tool_result: Any = None,
    **_kwargs: Any,
) -> None:
    """
    Hook chamado após cada tool use.
    Detecta quando uma decisão é registrada (claude-mem memory_add) e
    espelha no vault Obsidian.
    """
    global _session_decisions, _session_learnings

    if tool_name not in DECISION_TOOLS:
        return

    if not isinstance(tool_args, dict):
        return

    content = tool_args.get("content") or tool_args.get("narrative") or ""
    if not content:
        return

    title = tool_args.get("title") or content[:80]

    # Salva no vault como decisão
    decision_path = _save_decision(title, content)
    if decision_path:
        _session_decisions.append(decision_path)

    # Detecta se é um aprendizado
    content_lower = content.lower()
    if any(signal in content_lower for signal in LEARNING_SIGNALS):
        learning_path = _save_learning(title, content)
        if learning_path:
            _session_learnings.append(learning_path)


def _post_session_end(session_summary: str = "", **_kwargs: Any) -> None:
    """
    Hook chamado ao final da sessão.
    Atualiza current-state.md com o resumo da sessão.
    """
    global _session_decisions, _session_learnings

    if not session_summary:
        return

    _update_current_state(
        decisions=_session_decisions,
        learnings=_session_learnings,
        summary=session_summary,
    )

    _session_decisions.clear()
    _session_learnings.clear()


# ---------------------------------------------------------------------------
# Helpers de escrita no vault
# ---------------------------------------------------------------------------

def _save_decision(title: str, content: str) -> Optional[str]:
    """
    Salva uma decisão no vault: _decisions/YYYY-MM-DD-titulo.md
    Formato: frontmatter YAML + conteúdo da decisão.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    slug = (
        title.lower()
        .replace(" ", "-")
        .replace("/", "-")[:60]
        .strip("-")
    )
    filename = f"{today}-{slug}.md"
    filepath = os.path.join(DECISIONS_DIR, filename)

    os.makedirs(DECISIONS_DIR, exist_ok=True)

    note = f"""---
tags: [decision]
status: active
created: {today}
updated: {today}
source: hermes-session
---

# {title}

{content}
"""
    try:
        with open(filepath, "w") as f:
            f.write(note)
        return filepath
    except OSError:
        return None


def _save_learning(title: str, content: str) -> Optional[str]:
    """
    Salva um aprendizado no vault: _learnings/titulo.md
    """
    today = datetime.now().strftime("%Y-%m-%d")
    slug = (
        title.lower()
        .replace(" ", "-")
        .replace("/", "-")[:60]
        .strip("-")
    )
    filename = f"{today}-{slug}.md"
    filepath = os.path.join(LEARNINGS_DIR, filename)

    os.makedirs(LEARNINGS_DIR, exist_ok=True)

    note = f"""---
tags: [learning]
status: active
created: {today}
updated: {today}
source: hermes-session
---

# {title}

{content}
"""
    try:
        with open(filepath, "w") as f:
            f.write(note)
        return filepath
    except OSError:
        return None


def _update_current_state(
    decisions: List[str],
    learnings: List[str],
    summary: str,
) -> None:
    """
    Atualiza _memory/current-state.md com as decisões e aprendizados da sessão.
    Mantém o formato existente, adiciona nova seção da sessão atual.
    """
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)

    # Lê o arquivo existente
    existing = ""
    try:
        with open(MEMORY_FILE, "r") as f:
            existing = f.read()
    except FileNotFoundError:
        pass

    # Constrói o bloco da sessão
    decision_lines = ""
    for d in decisions[-5:]:  # últimas 5 decisões
        fname = os.path.basename(d).replace(".md", "")
        decision_lines += f"- Decisão: [[{fname}]]\n"

    learning_lines = ""
    for l in learnings[-5:]:
        fname = os.path.basename(l).replace(".md", "")
        learning_lines += f"- Aprendizado: [[{fname}]]\n"

    session_block = f"""

## Session: {today}

### Decisions
{decision_lines or '- Nenhuma decisão registrada'}
### Learnings
{learning_lines or '- Nenhum aprendizado registrado'}
### Summary
{summary[:500]}
"""

    # Atualiza o "Last Update" no topo
    updated = existing
    if "## Last Update:" in updated:
        import re
        updated = re.sub(
            r"## Last Update:.*",
            f"## Last Update: {today}",
            updated,
        )

    # Adiciona o bloco da sessão
    updated += session_block

    try:
        with open(MEMORY_FILE, "w") as f:
            f.write(updated)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Sync bidirecional: claude-mem → vault
# ---------------------------------------------------------------------------

def sync_claude_mem_to_vault():
    """
    Exporta observações recentes do claude-mem para o vault.
    Chamado via cron ou manualmente.
    """
    claude_mem_data = os.path.join(SINAPSE_HOME, "claude-mem", "data")
    db_path = os.path.join(claude_mem_data, "claude-mem.db")

    if not os.path.exists(db_path):
        return

    # Usa sqlite3 para ler observações recentes
    try:
        result = subprocess.run(
            [
                "sqlite3", db_path,
                "SELECT id, content, created_at FROM observations "
                "ORDER BY created_at DESC LIMIT 10;",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return

        for line in result.stdout.strip().split("\n"):
            parts = line.split("|", 2)
            if len(parts) >= 2:
                obs_id, content = parts[0], parts[1]
                # Salva como nota no vault
                _save_decision(
                    title=f"claude-mem observation {obs_id}",
                    content=content,
                )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass
