#!/usr/bin/env python3
"""
Sinapse Agent — MCP Server (stdio)
Expoe ferramentas de leitura e escrita do vault para qualquer agente MCP.

Uso:
  .venv/bin/python scripts/services/sinapse-mcp.py

Config MCP do agente:
  {
    "mcpServers": {
      "sinapse-memory": {
        "command": "<SINAPSE_HOME>/.venv/bin/python",
        "args": ["scripts/services/sinapse-mcp.py"],
        "cwd": "<SINAPSE_HOME>",
        "transport": "stdio"
      }
    }
  }
"""

import json
import sys
from pathlib import Path

# Bootstrap: adiciona project root ao sys.path para que `from core.X import ...`
# funcione quando o script é executado via `python /path/script.py` (systemd).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import paths as cp
from plugins.hermes import sinapse_memory as _sinapse_memory_adapter  # noqa: F401
from scripts.knowledge.sinapse_zettelkasten import split_monolithic_file
import sinapse_memory as sm

DEFAULT_ZETTEL_DIR = str(cp.TEMPORAL / "Hive-Mind" / "atoms")


def _load_instructions() -> str:
    """Carrega a política de uso do agente (fonte única em config/).
    O mesmo arquivo é injetado nos prompts dos agentes pelo register-mcp.sh."""
    try:
        p = Path(__file__).resolve().parents[2] / "config" / "sinapse-agent-prompt.md"
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return (
            "Hive-Mind (sinapse-memory): antes de responder sobre o projeto, "
            "consulte com sinapse_query/search_memories; salve decisões e "
            "aprendizados com sinapse_save_decision/sinapse_save_learning; chame "
            "sinapse_session_end ao fim. Use SOMENTE as tools sinapse_*."
        )


SINAPSE_INSTRUCTIONS = _load_instructions()

TOOLS = [
    {
        "name": "sinapse_query",
        "description": "Orquestrador cerebral e busca padrão para contexto de projeto — funde 7 backends via Context Fusion (paralelo, circuit breaker, timeout 8s): UMC (índice SQLite consolidado), NeuralMemory (associação), sqlite-vec (semântico local), claude-mem (eventos temporais), Graphify (estrutural/Leiden), Graphiti (causalidade temporal com validade) e filesystem scan. Use primeiro para entender estado/histórico/decisões/código/vault. Returns nodes, edges, observations e temporal facts do cérebro inteiro.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query in natural language (Portuguese or English)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "sinapse_save_decision",
        "description": "Save a decision to the anatomical Obsidian vault at cerebro/cortex/frontal/trabalho/ativo/. Creates a markdown file with YAML frontmatter (tags, status, created, source). Decisions become nodes in the knowledge graph after next index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Decision title"},
                "content": {
                    "type": "string",
                    "description": "Decision content — full context, reasoning, and implications"
                }
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "sinapse_save_learning",
        "description": "Save a learning, pattern, or insight to cerebro/cerebelo/padroes/Patterns.md. Automatically deduplicates — won't save if the same title already exists. Use for discovered patterns, lessons learned, or reusable insights.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Learning title"},
                "content": {
                    "type": "string",
                    "description": "Learning content — what was discovered and why it matters"
                }
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "sinapse_health",
        "description": "Health check for Sinapse. Returns read_backends with the 7 backends fused by sinapse_query (UMC, NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem), components with auxiliary/runtime availability, and vault status. RTK is NOT a read-backend; it appears only under components because it is a shell command optimizer and does NOT participate in sinapse_query.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "sinapse_session_end",
        "description": "End current session and update cerebro/cortex/frontal/brain/Current State.md with session summary and decisions/learnings. Should be called at the end of substantial work sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Session summary (max 500 chars)"
                }
            },
            "required": ["summary"]
        }
    },
    {
        "name": "sinapse_temporal_search",
        "description": "Step 1 of claude-mem temporal workflow: search the global temporal memory index (~/.claude-mem, /api/search). Use for recent prompts, conversations, sessions, and raw observations. Returns compact matches with IDs; then call sinapse_temporal_timeline for context and sinapse_temporal_get_observations only for filtered IDs. Prefer short, exact terms or titles found by sinapse_query. Empty results do not prove absence of memory: reduce the query or use sinapse_query/search_memories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for temporal memory"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default claude-mem behavior)"
                },
                "project": {
                    "type": "string",
                    "description": "Optional project filter (e.g. Hive-Mind)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "sinapse_temporal_timeline",
        "description": "Step 2 of claude-mem temporal workflow: get chronological context around an observation ID or a query-selected anchor (~/.claude-mem, /api/timeline). Use after sinapse_temporal_search found promising IDs/titles. Returns a compact window before/after the anchor; it still is not the full hydrated record.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "anchor": {
                    "type": "integer",
                    "description": "Observation ID to center the timeline around"
                },
                "query": {
                    "type": "string",
                    "description": "Query to let claude-mem choose an anchor automatically"
                },
                "depth_before": {
                    "type": "integer",
                    "description": "Items before anchor (default 3)"
                },
                "depth_after": {
                    "type": "integer",
                    "description": "Items after anchor (default 3)"
                },
                "project": {
                    "type": "string",
                    "description": "Optional project filter"
                }
            }
        }
    },
    {
        "name": "sinapse_temporal_get_observations",
        "description": "Step 3 of claude-mem temporal workflow: hydrate full observation details for filtered IDs only (~/.claude-mem, /api/observations/batch). Use after sinapse_temporal_search and/or sinapse_temporal_timeline narrowed the candidates. Do not call this with broad/unfiltered IDs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Observation IDs to fetch after filtering"
                },
                "orderBy": {
                    "type": "string",
                    "description": "Optional claude-mem ordering parameter"
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional max records"
                },
                "project": {
                    "type": "string",
                    "description": "Optional project filter"
                }
            },
            "required": ["ids"]
        }
    },
    {
        "name": "sinapse_temporal_save",
        "description": "Save a raw temporal observation. Direct HTTP write to claude-mem only works in server-beta mode (CLAUDE_MEM_RUNTIME=server-beta). In the normal worker runtime, claude-mem writes happen via hooks; this tool falls back to a vault learning note. Do not rely on it as the primary write path for current-session capture.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Observation content to save"
                },
                "kind": {
                    "type": "string",
                    "description": "Kind of observation: change, decision, learning, event (default: change)"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "sinapse_zettelkasten_split",
        "description": "Partition a monolithic markdown file into atomic Zettelkasten notes under the anatomical temporal cortex using local Ollama (qwen2.5-coder:3b). Requires source_file to exist and Ollama to be running. Runs graphify update as best-effort after writing atoms; graph update failure is logged but does not undo created files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_file": {
                    "type": "string",
                    "description": "Path to the monolithic markdown file to partition (e.g. cerebro/cerebelo/padroes/Patterns.md)"
                },
                "output_dir": {
                    "type": "string",
                    "description": f"Target atoms directory (default: {DEFAULT_ZETTEL_DIR})"
                }
            },
            "required": ["source_file"]
        }
    },
    {
        "name": "sinapse_capture_screen",
        "description": "Capture exactly one screenshot on explicit agent/user request and save it to the visual inbox (cerebro/cortex/parietal/inbox/visual/). Use only when visual context is necessary. Never use in loops or for monitoring. On multi-monitor setups, pass monitor explicitly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Required reason/context for the capture. Will be used in the filename."
                },
                "monitor": {
                    "type": "integer",
                    "description": "Physical monitor index to capture (1-based). Required when more than one monitor is connected."
                }
            },
            "required": ["description"]
        }
    },
    {
        "name": "sinapse_plan_goal",
        "description": "Decompose a goal into a small atomic checklist and persist it as an active work note in the frontal cortex. Use for planning a substantial objective, not for ordinary one-step tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Objetivo a ser decomposto em passos atômicos"
                },
                "context": {
                    "type": "string",
                    "description": "Contexto adicional opcional para auxiliar na decomposição"
                }
            },
            "required": ["goal"]
        }
    },
    {
        "name": "sinapse_temporal_graph_search",
        "description": "Compatibility tool for direct Graphiti/FalkorDB lookup over temporal/causal edges extracted from synthesized neurons. Prefer sinapse_query for normal work because it already fuses Graphiti with the other six backends. Use this only when debugging Graphiti specifically or when raw temporal graph edges are required. Requires FalkorDB on localhost:6379.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language query to search the temporal graph"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Max results to return (default 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_memories",
        "description": (
            "Busca neurônios consolidados do vault por similaridade semântica (HNSW cosine) "
            "ou texto literal. Use quando quiser arquivos/neurônios específicos, especialmente "
            "com filtro project. Modo 'semantic' usa embedding + índice HNSW; faz fallback "
            "automático para texto se o índice estiver ausente ou desatualizado (>7d). "
            "Retorna [{label, source_file, project, topic, score, aliases}]."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Consulta em linguagem natural (PT ou EN)"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Número máximo de resultados (default 10)",
                    "default": 10
                },
                "project": {
                    "type": "string",
                    "description": "Filtrar por projeto (ex: 'Hive-Mind'). Opcional."
                },
                "mode": {
                    "type": "string",
                    "enum": ["semantic", "text"],
                    "description": "Modo de busca: 'semantic' (HNSW, default) ou 'text' (full-text).",
                    "default": "semantic"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "sinapse_rag_query",
        "description": (
            "Consulta o índice LightRAG (grafo + vetor) sobre memórias consolidadas. "
            "Melhor para perguntas multi-hop entre entidades já indexadas. "
            "Depende do storage LightRAG estar populado em claude-mem/data/lightrag; "
            "se vier vazio/indisponível, use sinapse_query como fallback."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Pergunta em linguagem natural para consultar o grafo LightRAG"
                },
                "mode": {
                    "type": "string",
                    "enum": ["naive", "local", "global", "hybrid"],
                    "description": "Modo de busca: hybrid (grafo+vetor), local (entidades), global (comunidades), naive (vetor puro)",
                    "default": "hybrid"
                }
            },
            "required": ["question"]
        }
    }
]

HANDLERS = {
    "sinapse_query": lambda args: _sinapse_query_with_diagnostics(args.get("query", "")),
    "sinapse_save_decision": lambda args: {
        "saved": sm._save_decision(args.get("title", ""), args.get("content", "")) is not None
    },
    "sinapse_save_learning": lambda args: {
        "saved": sm._save_learning(args.get("title", ""), args.get("content", "")) is not None
    },
    "sinapse_health": lambda args: sm.health_check(),
    "sinapse_session_end": lambda args: _session_end(args.get("summary", "")),
    "sinapse_temporal_search": lambda args: _temporal_search(args),
    "sinapse_temporal_timeline": lambda args: _temporal_timeline(args),
    "sinapse_temporal_get_observations": lambda args: _temporal_get_observations(args),
    "sinapse_temporal_save": lambda args: _temporal_save(args.get("content", ""), args.get("kind", "change")),
    "sinapse_zettelkasten_split": lambda args: _zettelkasten_split(args.get("source_file", ""), args.get("output_dir", DEFAULT_ZETTEL_DIR)),
    "sinapse_capture_screen": lambda args: _capture_screen(
        args.get("description", ""),
        args.get("monitor"),
    ),
    "sinapse_plan_goal": lambda args: _plan_goal(args.get("goal", ""), args.get("context")),
    "sinapse_temporal_graph_search": lambda args: _temporal_graph_search(
        args.get("query", ""),
        num_results=int(args.get("num_results", 10)),
    ),
    "search_memories": lambda args: _search_memories(
        args.get("query", ""),
        top_k=int(args.get("top_k", 10)),
        project=args.get("project"),
        mode=args.get("mode", "semantic"),
    ),
    "sinapse_rag_query": lambda args: _rag_query(
        args.get("question", ""),
        mode=args.get("mode", "hybrid"),
    ),
}


def _session_end(summary):
    # Captura o buffer da sessão ANTES de zerar — senão as decisões/aprendizados
    # acumulados nunca chegam ao Current State (A3/P1-9)
    decisions = list(sm._session_decisions)
    learnings = list(sm._session_learnings)
    sm._session_decisions.clear()
    sm._session_learnings.clear()
    sm._update_current_state(decisions, learnings, summary)
    return {"updated": True}


def _rag_query(question: str, mode: str = "hybrid") -> dict:
    """
    Consulta o índice LightRAG sobre memórias consolidadas.

    Melhor para perguntas multi-hop que FTS5 não resolve (ex: "quais projetos
    mencionam X e qual sua relação com Y?"). Retorna string bruta ou vazio se
    LightRAG não estiver disponível (ImportError, sem LLM configurado, etc.).
    """
    try:
        from core.lightrag_index import query_rag_sync
        result = query_rag_sync(question, mode=mode)
        return {"result": result or "(LightRAG indisponível ou sem resultado)"}
    except Exception as e:
        return {"result": f"(LightRAG erro: {e})"}


def _sinapse_query_with_diagnostics(query: str) -> dict:
    """
    Orquestrador cerebral — funde todos os 7 backends registrados via
    Context Fusion (paralelo, circuit breaker, global timeout 8s).

    Antes (bug): chamava `sm._backend_umc(query)` — apenas 1 backend
    (UMC), quebrando a promessa da anatomia (cérebro federador com
    Graphify + claude-mem + NeuralMemory + filesystem + sqlite-vec +
    graphiti + umc).

    Agora: chama `sm._query_vault_knowledge(query)` que itera
    `_READ_BACKENDS` e funde os resultados. Quando TODOS os backends
    estão indisponíveis (orquestrador retorna None), devolve um dict
    de erro estruturado para o chamador MCP entender (sem exception
    silenciosa).
    """
    try:
        result = sm._query_vault_knowledge(query)
    except Exception as e:
        return {
            "source": "context-fusion",
            "observations": [],
            "query": query,
            "error": str(e),
            "error_type": type(e).__name__,
        }
    if result is None:
        return {
            "source": "context-fusion",
            "observations": [],
            "query": query,
            "error": "_query_vault_knowledge returned None (nenhum backend saudável)",
            "error_type": "BackendUnavailable",
        }
    return result


def _capture_screen(description="", monitor=None):
    """Captura tela via Screenpipe REST (primário) ou visual_capture.py (fallback)."""
    import os
    import subprocess

    # Tenta Screenpipe primeiro (zero overhead se não estiver rodando)
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts.capture.parsers.screenpipe import screenpipe_alive, capture_screenshot
        if screenpipe_alive():
            result = capture_screenshot(description, monitor=monitor)
            if result.get("path"):
                return {"success": True, **result}
    except Exception:
        pass

    # Fallback: visual_capture.py via subprocess
    scripts_dir = os.path.dirname(__file__)
    capture_script = os.path.normpath(os.path.join(scripts_dir, "..", "capture", "visual_capture.py"))
    cmd = [sys.executable, capture_script]
    if monitor is not None:
        cmd.extend(["--monitor", str(monitor)])
    if description:
        cmd.append(description)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        path = result.stdout.strip()
        return {"success": True, "path": path, "description": description, "source": "visual_capture"}
    except subprocess.CalledProcessError as e:
        return {"success": False, "error": e.stderr.strip() or str(e), "description": description}
    except Exception as e:
        return {"success": False, "error": str(e), "description": description}


def _zettelkasten_split(source_file, output_dir=DEFAULT_ZETTEL_DIR):
    """Split monolithic note into atomic Zettelkasten notes."""
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[2]
    # Resolve source_file relative to project root if not absolute
    src = Path(source_file)
    if not src.is_absolute():
        src = project_root / src
    src = src.resolve()
    if not src.exists():
        return {"error": f"Source file not found: {src}", "source_file": str(src)}
    # Resolve output_dir relative to project root if not absolute
    out = Path(output_dir)
    if not out.is_absolute():
        out = project_root / out
    out = out.resolve()
    files = split_monolithic_file(str(src), str(out))
    return {"atoms_created": len(files), "files": files}


CLAUDE_MEM_URL = "http://127.0.0.1:37700"


def _claude_mem_get(path: str, params: dict, timeout: int = 5) -> dict:
    """GET helper for the local claude-mem worker API."""
    from urllib.request import Request, urlopen
    from urllib.error import URLError
    from urllib.parse import urlencode

    clean = {k: v for k, v in params.items() if v not in (None, "")}
    try:
        suffix = f"?{urlencode(clean)}" if clean else ""
        req = Request(f"{CLAUDE_MEM_URL}{path}{suffix}", method="GET")
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return {"source": "claude-mem (temporal)", "results": data, "params": clean}
    except (URLError, json.JSONDecodeError, OSError) as e:
        return {"source": "claude-mem (temporal)", "error": str(e), "params": clean}


def _claude_mem_post(path: str, payload: dict, timeout: int = 5) -> dict:
    """POST helper for the local claude-mem worker API."""
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    try:
        req = Request(
            f"{CLAUDE_MEM_URL}{path}",
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return {"source": "claude-mem (temporal)", "results": data, "params": payload}
    except (URLError, json.JSONDecodeError, OSError) as e:
        return {"source": "claude-mem (temporal)", "error": str(e), "params": payload}


def _temporal_search(args):
    """Step 1: compact search/index over global claude-mem (/api/search)."""
    query = args.get("query", "")
    params = {
        "query": query,
        "limit": args.get("limit"),
        "project": args.get("project"),
    }
    result = _claude_mem_get("/api/search", params)
    result["query"] = query
    return result


def _temporal_timeline(args):
    """Step 2: timeline context around an observation ID or query anchor."""
    params = {
        "anchor": args.get("anchor"),
        "query": args.get("query"),
        "depth_before": args.get("depth_before", 3),
        "depth_after": args.get("depth_after", 3),
        "project": args.get("project"),
    }
    if not params.get("anchor") and not params.get("query"):
        return {
            "source": "claude-mem (temporal)",
            "error": "sinapse_temporal_timeline requires anchor or query",
            "params": params,
        }
    return _claude_mem_get("/api/timeline", params)


def _temporal_get_observations(args):
    """Step 3: hydrate full observation records for filtered IDs."""
    ids = args.get("ids", [])
    if not isinstance(ids, list) or not ids:
        return {
            "source": "claude-mem (temporal)",
            "error": "sinapse_temporal_get_observations requires non-empty ids array",
            "params": {"ids": ids},
        }
    payload = {k: v for k, v in args.items() if v not in (None, "")}
    return _claude_mem_post("/api/observations/batch", payload)


def _temporal_save(content, kind="change"):
    """Salva observação no claude-mem (modo server-beta) ou fallback vault."""
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    # Tenta server-beta primeiro
    try:
        req = Request(
            f"{CLAUDE_MEM_URL}/api/observations",
            method="POST",
            data=json.dumps({"content": content, "kind": kind}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return {"saved": True, "backend": "claude-mem", "content": content[:100]}
    except (URLError, OSError):
        pass

    # Fallback: salva como nota temporal no vault
    try:
        sm._save_learning(f"temporal: {content[:80]}", content)
        return {"saved": True, "backend": "vault (fallback)", "content": content[:100]}
    except Exception as e:
        return {"saved": False, "error": str(e)}


def _plan_goal(goal: str, context=None):
    """Decompõe objetivo em passos atômicos e persiste no Intent Memory.

    planner.py foi removido; usa decomposição inline mínima + escrita no vault.
    """
    import uuid
    from pathlib import Path

    # Decomposição minimal (4 passos atômicos)
    steps = [
        {"step": 1, "action": "Clarify objective boundaries", "expected_output": "Scope & constraints"},
        {"step": 2, "action": "Identify required inputs", "expected_output": "Dependency list"},
        {"step": 3, "action": "Decompose into atomic tasks", "expected_output": "Task list with acceptance criteria"},
        {"step": 4, "action": "Sequence and prioritize", "expected_output": "Execution order"},
    ]
    if context:
        steps.insert(0, {"step": 0, "action": f"Context review: {context}", "expected_output": "Context summary"})

    goal_id = f"goal-{uuid.uuid4().hex[:8]}"

    # Persist no vault como decisão atômica
    try:
        vault_dir = cp.WORK_ACTIVE
        vault_dir.mkdir(parents=True, exist_ok=True)
        f = vault_dir / f"{goal_id}.md"
        f.write_text(
            f"---\ntags: [plan, goal]\nstatus: active\ncreated: {__import__('datetime').date.today().isoformat()}\n---\n"
            f"# Goal: {goal}\n\n## Context\n{context or 'N/A'}\n\n## Steps\n"
            + "\n".join(f"- [ ] **S{s['step']}**: {s['action']} → {s['expected_output']}" for s in steps)
        )
    except Exception:
        pass  # vault write is best-effort; goal_id and steps are the contract

    return {"goal_id": goal_id, "steps": steps}


def _temporal_graph_search(query: str, num_results: int = 10):
    """Search Graphiti temporal graph via FalkorDB.

    DEPRECATED: esta tool é mantida para não quebrar clientes existentes,
    mas a consulta cerebral canônica é `sinapse_query` (que funde os
    7 órgãos via Context Fusion: UMC + NeuralMemory + sqlite-vec +
    claude-mem + Graphify + Graphiti + filesystem). Graphiti é apenas
    um dos órgãos que o cérebro funde — expor como tool separada quebra
    a anatomia. Será removida em release futura.
    """
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from integrations.graphiti import search_graph, graphiti_available
        if not graphiti_available():
            return {"source": "graphiti", "available": False, "results": [], "query": query}
        results = search_graph(query, num_results=num_results)
        return {"source": "graphiti", "available": True, "results": results, "query": query}
    except Exception as e:
        return {"source": "graphiti", "available": False, "error": str(e), "results": [], "query": query}


def _search_memories(query: str, top_k: int = 10, project=None, mode: str = "semantic"):
    """Busca neurônios via HNSW (semantic) ou full-text, com fallback automático."""
    from core.database import get_connection, ensure_migrations
    from core.search import search_neurons
    conn = get_connection()
    ensure_migrations(conn)
    try:
        return search_neurons(conn, query, top_k=top_k, project=project, mode=mode)
    finally:
        conn.close()


def handle_request(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "sinapse-memory", "version": "1.0.0"},
                "instructions": SINAPSE_INSTRUCTIONS,
            }
        }
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = HANDLERS.get(tool_name)
        if handler:
            from core.telemetry import span
            try:
                with span(f"mcp.{tool_name}", {"tool": tool_name}):
                    result = handler(tool_args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, default=str)}]
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                        "isError": True
                    }
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            }
    elif method == "notifications/initialized":
        return None
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"}
        }


def main():
    from core.telemetry import init_telemetry, flush_telemetry
    init_telemetry()
    # SIGTERM handler: em prod, MCP servers recebem SIGTERM (não KeyboardInterrupt)
    # do systemd/agente. Default Python termina SEM rodar `finally` ou `atexit`,
    # perdendo o flush de spans. Convertemos SIGTERM em KeyboardInterrupt para
    # cair no `except KeyboardInterrupt: break` abaixo.
    import signal
    try:
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    except (ValueError, OSError):
        # SIGTERM só pode ser tratado no main thread; em testes/imports pode
        # falhar silenciosamente.
        pass
    try:
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                req = json.loads(line.strip())
                resp = handle_request(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError:
                continue
            except KeyboardInterrupt:
                break
    finally:
        flush_telemetry()


if __name__ == "__main__":
    main()
