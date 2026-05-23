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
import sys
import tempfile
import time
import traceback
import unicodedata
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

SINAPSE_HOME = os.environ.get(
    "SINAPSE_HOME",
    os.path.expanduser("~/Documentos/Projects/sinapse_agent"),
)
VAULT_DIR = os.path.join(SINAPSE_HOME, "cerebro")
GRAPH_JSON = os.path.join(VAULT_DIR, "graphify-out", "graph.json")
DECISIONS_DIR = os.path.join(VAULT_DIR, "work", "active")
MEMORY_FILE = os.path.join(VAULT_DIR, "brain", "Current State.md")
PROJECTS_DIR = os.path.join(VAULT_DIR, "work", "active")
PATTERNS_FILE = os.path.join(VAULT_DIR, "brain", "Patterns.md")

# Claude-mem HTTP API
CLAUDE_MEM_URL = "http://127.0.0.1:37700"
CLAUDE_MEM_TIMEOUT = 3  # segundos — fallback rápido se offline

# NeuralMemory CLI
NMEM_BIN = os.path.expanduser("~/.local/bin/nmem")
NMEM_TIMEOUT = 5  # segundos

# Timeouts e limites — centralizados e documentados
GLOBAL_QUERY_TIMEOUT = 8       # segundos — orçamento total
MAX_CONTEXT_CHARS = 3000        # limite de injeção no prompt
MAX_NODES = 5                   # máximo de nodes na resposta
MAX_OBSERVATIONS = 5            # máximo de observations
OBSERVATION_CHARS = 300         # caracteres por observation (consistente)
SEMANTIC_CONTEXT_CHARS = 500    # caracteres do contexto semântico

# Decision tools: configurável via SINAPSE_DECISION_TOOLS env var
_DEFAULT_DECISION_TOOLS = {"memory_add", "observation_add", "mcp_claude_mem_memory_add"}
_custom_tools = os.environ.get("SINAPSE_DECISION_TOOLS", "")
if _custom_tools:
    DECISION_TOOLS = set(t.strip() for t in _custom_tools.split(","))
else:
    DECISION_TOOLS = _DEFAULT_DECISION_TOOLS

# Learning signals: configurável via SINAPSE_LEARNING_SIGNALS env var
_DEFAULT_LEARNING_SIGNALS = [
    # Português
    "aprendizado", "aprendizagem", "lição", "lição aprendida",
    "descoberta", "padrão identificado",
    # Inglês
    "learning", "insight", "pattern", "lesson",
    "lesson learned", "takeaway", "finding", "aha",
    "note to self", "tl;dr",
    # Espanhol (comum em times LATAM)
    "aprendizaje", "lección", "descubrimiento",
]
_custom_signals = os.environ.get("SINAPSE_LEARNING_SIGNALS", "")
if _custom_signals:
    LEARNING_SIGNALS = [s.strip().lower() for s in _custom_signals.split(",")]
else:
    LEARNING_SIGNALS = _DEFAULT_LEARNING_SIGNALS

# Dry-run mode: sem side effects no filesystem
DRY_RUN = os.environ.get("SINAPSE_DRY_RUN", "").lower() in ("1", "true", "yes")

# Log JSON estruturado
_LOG_JSON = os.environ.get("SINAPSE_LOG_JSON", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Logging estruturado
# ---------------------------------------------------------------------------

def _log(level: str, event: str, **kwargs):
    """Log estruturado opcional. Sempre loga em stderr."""
    if _LOG_JSON:
        entry = {"ts": datetime.now().isoformat(), "level": level, "event": event, **kwargs}
        print(json.dumps(entry), file=sys.stderr)
    else:
        extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
        print(f"[sinapse] {level.upper()}: {event} {extra}".strip(), file=sys.stderr)


# ---------------------------------------------------------------------------
# Config centralizada via sinapse.yaml
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Carrega sinapse.yaml se disponível."""
    config_path = os.path.join(SINAPSE_HOME, "sinapse.yaml")
    if os.path.isfile(config_path):
        try:
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f)
        except Exception:
            pass
    return {}

_config = _load_config()


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

_READ_BACKENDS: List[BackendFn] = []


def register_backend(fn: BackendFn) -> None:
    """Registra um backend de busca. Ordem de registro = prioridade."""
    if fn not in _READ_BACKENDS:
        _READ_BACKENDS.append(fn)


# ---------------------------------------------------------------------------
# Circuit Breaker (Fase 3.4)
# ---------------------------------------------------------------------------

_backend_state: Dict[str, Dict[str, Any]] = {}

def _is_backend_healthy(name: str) -> bool:
    """Circuit breaker simples: pula backends com falhas recentes."""
    state = _backend_state.get(name, {})
    failures = state.get("failures", 0)
    last_failure = state.get("last_failure", 0)
    cooldown = state.get("cooldown", 30)

    if failures >= 3 and (time.time() - last_failure) < cooldown:
        _log("warn", "circuit_breaker_open", backend=name, failures=failures)
        return False
    return True

def _record_backend_result(name: str, success: bool):
    state = _backend_state.setdefault(name, {"failures": 0, "last_failure": 0, "cooldown": 30})
    if success:
        state["failures"] = 0
    else:
        state["failures"] += 1
        state["last_failure"] = time.time()


# ---------------------------------------------------------------------------
# Backend 0: NeuralMemory (associativo — spreading activation)
# ---------------------------------------------------------------------------

def _backend_neural_memory(query: str) -> Optional[Dict[str, Any]]:
    """
    Busca associativa via NeuralMemory (spreading activation).
    Chama `nmem recall <query>` e parseia o output.
    Tenta formato --json primeiro, fallback para parser de texto.
    """
    if not os.path.isfile(NMEM_BIN) or not os.access(NMEM_BIN, os.X_OK):
        return None

    # Tenta formato JSON primeiro (mais recente do nmem)
    try:
        result = subprocess.run(
            [NMEM_BIN, "recall", "--json", query],
            capture_output=True,
            text=True,
            timeout=NMEM_TIMEOUT,
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                memories = data if isinstance(data, list) else data.get("memories", [])
                if memories:
                    return {
                        "source": "neural-memory (associative)",
                        "observations": [
                            {"content": m.get("content", str(m)), "confidence": m.get("confidence", 0.5)}
                            for m in memories[:MAX_OBSERVATIONS]
                        ],
                        "count": len(memories),
                        "query": query,
                    }
            except json.JSONDecodeError:
                pass  # fallback para parser de texto
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Fallback: parser de texto (formato atual)
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
                    "observations": [{"content": context[:SEMANTIC_CONTEXT_CHARS]}],
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
                        {"title": i.get("title", ""), "content": i.get("excerpt", "")[:OBSERVATION_CHARS]}
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

# Cache de graph.json com TTL (Fase 3.2)
_graph_cache: Dict[str, Any] = {}
_graph_cache_time: float = 0
_GRAPH_CACHE_TTL = 60  # segundos


def _validate_graph_schema(graph: dict) -> bool:
    """Valida que o graph.json tem a estrutura esperada."""
    if not isinstance(graph, dict):
        return False
    nodes = graph.get("nodes")
    links = graph.get("links")
    if not isinstance(nodes, list) or not isinstance(links, list):
        return False
    if nodes:
        required_keys = {"label", "id"}
        if not required_keys.issubset(nodes[0].keys()):
            return False
    return True


def _load_graph() -> Optional[dict]:
    """Carrega graph.json com cache TTL (Fase 3.2)."""
    global _graph_cache, _graph_cache_time

    if not os.path.isfile(GRAPH_JSON):
        return None

    now = time.time()
    if _graph_cache and (now - _graph_cache_time) < _GRAPH_CACHE_TTL:
        return _graph_cache

    try:
        with open(GRAPH_JSON, "r") as f:
            _graph_cache = json.load(f)
        _graph_cache_time = now
        return _graph_cache
    except (json.JSONDecodeError, OSError):
        return None


def _backend_graphify(query: str) -> Optional[Dict[str, Any]]:
    """
    Busca estrutural no knowledge graph (graph.json).
    Busca textual nos labels e tipos dos nodes/edges.
    Implementa retry loop para race condition cron vs plugin (Fase 1.2).
    """
    if not os.path.isfile(GRAPH_JSON):
        return None

    # Retry loop: graph.json pode estar sendo escrito pelo cron
    graph = None
    for attempt in range(3):
        try:
            with open(GRAPH_JSON, "r") as f:
                graph = json.load(f)
            break
        except (json.JSONDecodeError, OSError):
            if attempt < 2:
                time.sleep(0.1)
            else:
                _log("error", "graph_json_read_failed", file=GRAPH_JSON)
                return None

    if graph is None:
        return None

    if not _validate_graph_schema(graph):
        _log("error", "graph_schema_invalid")
        return None

    words = set(_normalize(query).split())
    matched_nodes = []
    matched_edges = []

    for node in graph.get("nodes", []):
        label = _normalize(node.get("label") or "")
        node_type = _normalize(node.get("file_type") or "")
        community = _normalize(str(node.get("community", "")))
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
# Motor de busca unificado (com exception logging + global timeout)
# ---------------------------------------------------------------------------

def _query_vault_knowledge(query: str) -> Optional[Dict[str, Any]]:
    """
    Orquestra todos os backends em ordem de prioridade.
    Retorna o primeiro resultado não-vazio.
    Implementa:
      - Exception logging (Fase 1.1)
      - Circuit breaker (Fase 3.4)
      - Global timeout budget (Fase 3.7)
    """
    if not query or not query.strip():
        return None

    deadline = time.time() + GLOBAL_QUERY_TIMEOUT

    for backend in _READ_BACKENDS:
        if time.time() > deadline:
            _log("warn", "query_timeout", query=query[:50])
            break

        name = backend.__name__

        if not _is_backend_healthy(name):
            continue

        try:
            result = backend(query)
            if result:
                _record_backend_result(name, True)
                _log("info", "backend_hit", backend=name, query=query[:50])
                return result
            _record_backend_result(name, False)
        except (URLError, OSError, subprocess.TimeoutExpired, FileNotFoundError):
            # Expected: backend unreachable — silently skip
            _record_backend_result(name, False)
            continue
        except Exception as e:
            # Unexpected: bug in backend — log and skip
            _log("error", "backend_error", backend=name, error=str(e))
            traceback.print_exc(file=sys.stderr)
            _record_backend_result(name, False)
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

# Buffer acumulado durante a sessão
_session_decisions: List[str] = []
_session_learnings: List[str] = []


# ---------------------------------------------------------------------------
# Atomic write helper (Fase 1.3)
# ---------------------------------------------------------------------------

def _atomic_write(filepath: str, content: str) -> bool:
    """Escreve arquivo atomicamente via temp + rename."""
    dirname = os.path.dirname(filepath)
    os.makedirs(dirname, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dirname, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, filepath)  # atômico no Linux
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Slug sanitization (Fase 1.4)
# ---------------------------------------------------------------------------

def _sanitize_slug(title: str, max_len: int = 60) -> str:
    """Sanitiza título para slug de arquivo seguro."""
    # Normaliza unicode (remove acentos, converte ç→c, etc.)
    text = unicodedata.normalize("NFKD", title)
    text = text.encode("ASCII", "ignore").decode("ASCII")
    # Substitui qualquer caractere não alfanumérico por hífen
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text)
    # Remove hífens das bordas
    text = text.strip("-")
    # Trunca em boundary de palavra
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0]
    # Fallback se ficar vazio
    return text or "decision"


# ---------------------------------------------------------------------------
# Frontmatter validation (Fase 3.8)
# ---------------------------------------------------------------------------

def _validate_frontmatter_yaml(content: str) -> bool:
    """Verifica se o frontmatter YAML é válido."""
    if not content.startswith("---"):
        return False
    try:
        parts = content.split("---", 2)
        if len(parts) < 3:
            return False
        yaml_content = parts[1].strip()
        return all(k in yaml_content for k in ("tags:", "status:", "created:"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def _save_decision(title: str, content: str) -> Optional[str]:
    """
    Salva uma decisão no vault: work/active/YYYY-MM-DD-titulo.md
    Formato: frontmatter YAML + conteúdo da decisão.
    """
    if DRY_RUN:
        _log("info", "dry_run", action="save_decision", title=title[:60])
        return "/dev/null/dry-run"

    today = datetime.now().strftime("%Y-%m-%d")
    slug = _sanitize_slug(title)
    filename = f"{today}-{slug}.md"
    filepath = os.path.join(DECISIONS_DIR, filename)

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
    if not _validate_frontmatter_yaml(note):
        _log("error", "frontmatter_invalid", file=filepath)

    if _atomic_write(filepath, note):
        _log("info", "decision_saved", title=title[:60], file=filepath)
        return filepath

    _log("error", "save_decision_failed", title=title[:60], file=filepath)
    return None


def _save_learning(title: str, content: str) -> Optional[str]:
    """
    Salva um aprendizado no vault: append em brain/Patterns.md
    Com deduplicação (Fase 2.1).
    """
    if DRY_RUN:
        _log("info", "dry_run", action="save_learning", title=title[:60])
        return "/dev/null/dry-run"

    today = datetime.now().strftime("%Y-%m-%d")

    # Verifica duplicação
    try:
        with open(PATTERNS_FILE, "r") as f:
            existing = f.read()
        if title in existing:
            _log("info", "learning_duplicate_skipped", title=title[:60])
            return None
    except FileNotFoundError:
        pass

    entry = f"""

---

## {title} ({today})

{content}
"""
    try:
        with open(PATTERNS_FILE, "a") as f:
            f.write(entry)
        _log("info", "learning_saved", title=title[:60])
        return PATTERNS_FILE
    except OSError as e:
        _log("error", "save_learning_failed", title=title[:60], error=str(e))
        return None


def _update_current_state(
    decisions: List[str],
    learnings: List[str],
    summary: str,
) -> None:
    """
    Atualiza brain/Current State.md com as decisões e aprendizados da sessão.
    Mantém o formato existente, adiciona nova seção da sessão atual.
    Regex corrigido com flag MULTILINE (Fase 1.6).
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
    for d in decisions[-5:]:
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

    # Update "Last Update" — usa MULTILINE para casar até fim da linha (Fase 1.6)
    updated = existing
    updated = re.sub(
        r"^## Last Update:.*$",
        f"## Last Update: {today}",
        updated,
        flags=re.MULTILINE,
    )
    if "## Last Update:" not in updated:
        updated = f"## Last Update: {today}\n\n{updated}"

    updated += session_block

    if not _atomic_write(MEMORY_FILE, updated):
        _log("error", "update_current_state_failed", file=MEMORY_FILE)


# ===========================================================================
# HOOKS
# ===========================================================================

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
# Sync bidirecional: claude-mem → vault (via HTTP API — Fase 2.5)
# ---------------------------------------------------------------------------

def sync_claude_mem_to_vault():
    """Exporta observações recentes do claude-mem para o vault via API HTTP."""
    try:
        req = Request(
            f"{CLAUDE_MEM_URL}/api/search?query=&limit=10",
            method="GET",
        )
        with urlopen(req, timeout=CLAUDE_MEM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("items", [])
            for item in items:
                obs_id = item.get("id", "unknown")
                content = item.get("content") or item.get("excerpt", "")
                if content:
                    _save_decision(
                        title=f"claude-mem observation {obs_id}",
                        content=content,
                    )
    except (URLError, OSError, json.JSONDecodeError, ValueError) as e:
        _log("error", "claude_mem_sync_failed", error=str(e))


# ---------------------------------------------------------------------------
# Health check unificado (Fase 3.1)
# ---------------------------------------------------------------------------

def _check_nmem() -> bool:
    return os.path.isfile(NMEM_BIN) and os.access(NMEM_BIN, os.X_OK)

def _check_graphify() -> bool:
    return os.path.isfile(GRAPH_JSON)

def _check_rtk() -> bool:
    try:
        subprocess.run(["rtk", "--version"], capture_output=True, timeout=2)
        return True
    except Exception:
        return False

def _check_claude_mem() -> bool:
    try:
        req = Request(f"{CLAUDE_MEM_URL}/health", method="GET")
        with urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "ok"
    except Exception:
        return False

def _get_graph_node_count() -> int:
    try:
        with open(GRAPH_JSON) as f:
            return len(json.load(f).get("nodes", []))
    except Exception:
        return 0

def health_check() -> Dict[str, Any]:
    """Retorna status completo de todos os backends e componentes."""
    status = {
        "timestamp": datetime.now().isoformat(),
        "backends": {
            "neural_memory": _check_nmem(),
            "claude_mem": _check_claude_mem(),
            "graphify": _check_graphify(),
            "rtk": _check_rtk(),
        },
        "vault": {
            "path": VAULT_DIR,
            "exists": os.path.isdir(VAULT_DIR),
            "graph_nodes": _get_graph_node_count(),
        },
        "plugin": {
            "backends_registered": len(_READ_BACKENDS),
        },
    }
    status["healthy"] = all(
        v for v in status["backends"].values()
    )
    return status


# ---------------------------------------------------------------------------
# Module exports for testability
# ---------------------------------------------------------------------------

__all__ = [
    "register_backend",
    "health_check",
    "sync_claude_mem_to_vault",
    "_pre_prompt_build",
    "_post_tool_use",
    "_post_session_end",
    "_query_vault_knowledge",
    "_backend_graphify",
    "_backend_claude_mem",
    "_backend_neural_memory",
    "_save_decision",
    "_save_learning",
    "_update_current_state",
    "_format_context",
    "_sanitize_slug",
    "_atomic_write",
    "_normalize",
    "_validate_graph_schema",
    "_validate_frontmatter_yaml",
    "_load_graph",
    "_log",
    "SINAPSE_HOME",
    "VAULT_DIR",
    "GRAPH_JSON",
    "DECISIONS_DIR",
    "MEMORY_FILE",
    "PATTERNS_FILE",
    "MAX_NODES",
    "MAX_OBSERVATIONS",
    "MAX_CONTEXT_CHARS",
    "NMEM_BIN",
    "NMEM_TIMEOUT",
]
