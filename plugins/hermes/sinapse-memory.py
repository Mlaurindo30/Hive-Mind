"""
Sinapse Agent — Plugin de Memória para Hermes
=====================================================
Integração bidirecional entre Hermes, Obsidian vault, Graphify, claude-mem e NeuralMemory.

Arquitetura de backends plugáveis:
  LEITURA (pre_prompt_build):
    1. NeuralMemory (nmem recall) → busca associativa (spreading activation)
    2. claude-mem (HTTP API) → busca semântica temporal (Chroma + FTS5)
    3. graph.json (Graphify) → busca estrutural (Leiden clustering)
    4. Fallback vazio se nada disponível

  ESCRITA (post_tool_use + post_session_end):
    1. Decisão tomada → salva em cerebro/work/active/YYYY-MM-DD-titulo.md
    2. Aprendizado → salva em cerebro/brain/Patterns.md (append)
    3. Estado atualizado → cerebro/brain/Current State.md
    4. Notas salvas com frontmatter YAML + WikiLinks

Tudo converge no vault Obsidian como fonte única.
"""

import json
import os
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

SINAPSE_HOME = os.path.expanduser("~/Documentos/Projects/sinapse_agent")
VAULT_DIR = os.path.join(SINAPSE_HOME, "cerebro")
GRAPH_JSON = os.path.join(VAULT_DIR, "graphify-out", "graph.json")
DECISIONS_DIR = os.path.join(VAULT_DIR, "work", "active")
MEMORY_FILE = os.path.join(VAULT_DIR, "brain", "Current State.md")
PROJECTS_DIR = os.path.join(VAULT_DIR, "work", "active")
PATTERNS_FILE = os.path.join(VAULT_DIR, "brain", "Patterns.md")

# Claude-mem HTTP API
CLAUDE_MEM_URL = "http://127.0.0.1:37700"
CLAUDE_MEM_TIMEOUT = 3  # segundos — fallback rápido se offline

# Limites de injeção no prompt
MAX_CONTEXT_CHARS = 3000
MAX_NODES = 5
MAX_OBSERVATIONS = 5

# NeuralMemory CLI
NMEM_BIN = os.path.expanduser("~/.local/bin/nmem")
NMEM_TIMEOUT = 5  # segundos


# ---------------------------------------------------------------------------
# Helpers de normalização
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Remove acentos e normaliza para lowercase (busca cross-idioma)."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ASCII", "ignore").decode("ASCII")
    return text.lower()


# ---------------------------------------------------------------------------
# Sistema de Backends Plugáveis
# ---------------------------------------------------------------------------

BackendFn = Callable[[str], Optional[Dict[str, Any]]]

# Registro global de backends de leitura (ordem = prioridade)
_READ_BACKENDS: List[BackendFn] = []


def register_backend(fn: BackendFn) -> None:
    """Registra um backend de busca. Ordem de registro = prioridade."""
    if fn not in _READ_BACKENDS:
        _READ_BACKENDS.append(fn)


# ---------------------------------------------------------------------------
# Backend 0: NeuralMemory (associativo — spreading activation)
# ---------------------------------------------------------------------------

def _backend_neural_memory(query: str) -> Optional[Dict[str, Any]]:
    """
    Busca associativa via NeuralMemory (spreading activation).
    Chama `nmem recall <query>` e parseia o output.
    """
    if not os.path.isfile(NMEM_BIN) or not os.access(NMEM_BIN, os.X_OK):
        return None

    try:
        result = subprocess.run(
            [NMEM_BIN, "recall", query],
            capture_output=True,
            text=True,
            timeout=NMEM_TIMEOUT,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        # Parser simples do output do nmem recall
        lines = result.stdout.strip().split("\n")
        memories = []
        current = None
        for line in lines:
            line = line.strip()
            if line.startswith("- ") and not line.startswith("- ["):
                if current:
                    memories.append(current)
                current = {"content": line[2:].strip()}
            elif line.startswith("  [") and current:
                # Metadata line: [type] content [src=... · date · conf=...]
                meta = line.strip()
                if "conf=" in meta:
                    try:
                        conf_str = meta.split("conf=")[1].split("]")[0]
                        current["confidence"] = float(conf_str)
                    except (ValueError, IndexError):
                        pass
                if "src=" in meta:
                    try:
                        current["source"] = meta.split("src=")[1].split("·")[0].strip().rstrip("]")
                    except IndexError:
                        pass
        if current:
            memories.append(current)

        if not memories:
            # Tenta extrair da seção "## Relevant Memories"
            in_section = False
            for line in lines:
                if "## Relevant Memories" in line:
                    in_section = True
                    continue
                if in_section and line.startswith("- ") and line.strip() != "-":
                    memories.append({"content": line.strip()[2:]})
                elif in_section and line.startswith("##"):
                    break

        if not memories:
            return None

        return {
            "source": "neural-memory (associative)",
            "observations": [
                {"content": m.get("content", str(m)), "confidence": m.get("confidence", 0.5)}
                for m in memories[:MAX_OBSERVATIONS]
            ],
            "count": len(memories),
            "query": query,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


register_backend(_backend_neural_memory)


# ---------------------------------------------------------------------------
# Backend 1: claude-mem (semântico/temporal via Chroma + FTS5)
# ---------------------------------------------------------------------------

def _backend_claude_mem(query: str) -> Optional[Dict[str, Any]]:
    """
    Busca semântica no claude-mem via HTTP API.
    Tenta /api/context/semantic primeiro (Chroma), fallback /api/search (FTS5).
    """
    try:
        # Tenta busca semântica (Chroma embeddings)
        req = Request(
            f"{CLAUDE_MEM_URL}/api/context/semantic",
            data=json.dumps({"query": query}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=CLAUDE_MEM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            context = data.get("context", "")
            count = data.get("count", 0)
            if context and count > 0:
                return {
                    "source": "claude-mem (semantic)",
                    "observations": [{"content": context[:500]}],
                    "count": count,
                    "query": query,
                }
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        pass

    # Fallback: busca FTS5 textual
    try:
        encoded_query = quote(query)
        req = Request(
            f"{CLAUDE_MEM_URL}/api/search?query={encoded_query}",
            method="GET",
        )
        with urlopen(req, timeout=CLAUDE_MEM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("items", [])
            if items:
                return {
                    "source": "claude-mem (FTS5)",
                    "observations": [
                        {"title": i.get("title", ""), "content": i.get("excerpt", "")[:300]}
                        for i in items[:MAX_OBSERVATIONS]
                    ],
                    "count": len(items),
                    "query": query,
                }
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        pass

    return None


register_backend(_backend_claude_mem)


# ---------------------------------------------------------------------------
# Backend 2: Graphify (estrutural via graph.json)
# ---------------------------------------------------------------------------

def _backend_graphify(query: str) -> Optional[Dict[str, Any]]:
    """
    Busca estrutural no knowledge graph (graph.json).
    Busca textual nos labels e tipos dos nodes/edges.
    """
    if not os.path.isfile(GRAPH_JSON):
        return None

    try:
        with open(GRAPH_JSON, "r") as f:
            graph = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    words = set(_normalize(query).split())
    matched_nodes = []
    matched_edges = []

    for node in graph.get("nodes", []):
        label = _normalize(node.get("label") or "")
        node_type = _normalize(node.get("file_type") or "")
        community = _normalize(str(node.get("community", "")))
        # Busca em label, tipo, e comunidade
        if any(w in label or w in node_type or w in community for w in words):
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
        source = _normalize(link.get("source") or "")
        target = _normalize(link.get("target") or "")
        rel = _normalize(link.get("relation") or "")
        if any(w in source or w in target or w in rel for w in words):
            matched_edges.append({
                "source": link.get("source"),
                "target": link.get("target"),
                "relation": link.get("relation"),
            })

    if not matched_nodes and not matched_edges:
        return None

    return {
        "source": "graphify (structural)",
        "nodes": matched_nodes,
        "edges": matched_edges[:MAX_NODES],
        "query": query,
        "stats": {
            "total_nodes": len(graph.get("nodes", [])),
            "total_edges": len(graph.get("links", [])),
        },
    }


register_backend(_backend_graphify)


# ---------------------------------------------------------------------------
# Motor de busca unificado
# ---------------------------------------------------------------------------

def _query_vault_knowledge(query: str) -> Optional[Dict[str, Any]]:
    """
    Orquestra todos os backends em ordem de prioridade.
    Retorna o primeiro resultado não-vazio.
    """
    if not query or not query.strip():
        return None

    for backend in _READ_BACKENDS:
        try:
            result = backend(query)
            if result:
                return result
        except Exception:
            continue

    return None


# ---------------------------------------------------------------------------
# Formatação de contexto para injeção no prompt
# ---------------------------------------------------------------------------

def _format_context(ctx: Dict[str, Any]) -> str:
    """Formata contexto do vault para injeção no prompt (conciso)."""
    source = ctx.get("source", "sinapse")
    lines = [f"[Sinapse — {source}]"]

    # Formato: claude-mem observations
    for obs in ctx.get("observations", []):
        title = obs.get("title", "")
        content = obs.get("content", "")
        if title:
            lines.append(f"  • {title}")
        if content:
            lines.append(f"    {content[:200]}")

    # Formato: graphify nodes + edges
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


# ---------------------------------------------------------------------------
# Registro no Hermes
# ---------------------------------------------------------------------------

def register(ctx):
    """Registra hooks de leitura e escrita no Hermes."""
    ctx.register_hook("pre_prompt_build", _pre_prompt_build)       # leitura
    ctx.register_hook("post_tool_use", _post_tool_use)             # escrita
    ctx.register_hook("post_session_end", _post_session_end)       # escrita final


# ===========================================================================
# LEITURA — injeta contexto do vault no prompt
# ===========================================================================

def _pre_prompt_build(
    user_message: str = "",
    system_message: str = "",
    memory_context: str = "",
    **_kwargs: Any,
) -> Dict[str, Any]:
    """Busca contexto relevante em todos os backends e injeta no prompt."""
    result: Dict[str, Any] = {}

    if not user_message or not user_message.strip():
        return result

    context = _query_vault_knowledge(user_message)
    if context:
        block = _format_context(context)
        system_message = f"{block}\n\n---\n\n{system_message}" if system_message else block
        result["system_message"] = system_message

    return result


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
    Salva uma decisão no vault: work/active/YYYY-MM-DD-titulo.md
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
    Salva um aprendizado no vault: append em brain/Patterns.md
    """
    today = datetime.now().strftime("%Y-%m-%d")
    entry = f"""

---

## {title} ({today})

{content}
"""
    try:
        with open(PATTERNS_FILE, "a") as f:
            f.write(entry)
        return PATTERNS_FILE
    except OSError:
        return None


def _update_current_state(
    decisions: List[str],
    learnings: List[str],
    summary: str,
) -> None:
    """
    Atualiza brain/Current State.md com as decisões e aprendizados da sessão.
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
                _save_decision(
                    title=f"claude-mem observation {obs_id}",
                    content=content,
                )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass


# ---------------------------------------------------------------------------
# Health check (útil pra diagnosticar backends)
# ---------------------------------------------------------------------------

def health_check() -> Dict[str, Any]:
    """Retorna status de todos os backends."""
    status = {
        "graph_json": os.path.isfile(GRAPH_JSON),
        "claude_mem_reachable": False,
        "backends_registered": len(_READ_BACKENDS),
    }
    try:
        req = Request(f"{CLAUDE_MEM_URL}/health", method="GET")
        with urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            status["claude_mem_reachable"] = data.get("status") == "ok"
    except Exception:
        pass
    return status
