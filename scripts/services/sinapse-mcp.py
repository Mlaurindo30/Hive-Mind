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
import importlib.util

# Only load the plugin module if not already loaded (prevents re-registering backends)
if "sinapse_memory" not in sys.modules:
    _plugin_path = Path(__file__).resolve().parent.parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
    spec = importlib.util.spec_from_file_location("sinapse_memory", _plugin_path)
    sm = importlib.util.module_from_spec(spec)
    sys.modules["sinapse_memory"] = sm
    spec.loader.exec_module(sm)
else:
    import sinapse_memory as sm


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
        "description": "Orquestrador cerebral — funde 7 backends via Context Fusion (paralelo, circuit breaker, timeout 8s): UMC (índice SQLite consolidado), NeuralMemory (associação), sqlite-vec (semântico local), claude-mem (eventos temporais), Graphify (estrutural/Leiden), Graphiti (causalidade temporal com validade) e filesystem scan. Returns nodes, edges, observations e temporal facts do cérebro inteiro.",
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
        "description": "Save a decision to the Obsidian vault (cerebro/work/active/). Creates a markdown file with YAML frontmatter (tags, status, created, source). Decisions become nodes in the knowledge graph after next index.",
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
        "description": "Save a learning, pattern, or insight to cerebro/brain/Patterns.md. Automatically deduplicates — won't save if the same title already exists. Use for discovered patterns, lessons learned, or reusable insights.",
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
        "description": "Health check of all Sinapse read-backends (UMC, NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem — the 7 backends fused by sinapse_query) and vault status. RTK is NOT a read-backend (it's a shell optimizer); it appears in execution layer, not query layer. Returns node count and backend availability.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "sinapse_session_end",
        "description": "End current session and update brain/Current State.md with session summary and decisions/learnings. Should be called at the end of substantial work sessions.",
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
        "description": "Search claude-mem temporal memory directly (FTS5 full-text + Chroma semantic). Use for finding past conversations, events, and observations that may not be in the vault yet. Returns timeline entries and observations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for temporal memory"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "sinapse_temporal_save",
        "description": "Save an observation to claude-mem temporal memory. NOTE: only works when claude-mem is in server-beta mode (CLAUDE_MEM_RUNTIME=server-beta). In worker mode, observations are saved via hooks, not HTTP API. Falls back to saving in vault brain/Patterns.md as a temporal note.",
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
        "description": "Auto-partition a monolithic file or densly annotated content into individual conceptual atomic Zettelkasten notes in Obsidian vault atoms/ directory using local Ollama model (qwen2.5-coder:3b). Updates knowledge graph automatically.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_file": {
                    "type": "string",
                    "description": "Path to the monolithic markdown file to partition (e.g. cerebro/brain/Patterns.md)"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Target atoms directory (default: cerebro/atoms)"
                }
            },
            "required": ["source_file"]
        }
    },
    {
        "name": "sinapse_capture_screen",
        "description": "Capture exactly one screenshot on explicit agent/user request and save it to the vault (cerebro/inbox/visual/). Use only when visual context is necessary. Never use in loops or for monitoring. On multi-monitor setups, pass monitor explicitly.",
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
        "description": "Decompõe um objetivo em passos atômicos e salva no Intent Memory",
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
        "description": "Search the Graphiti temporal knowledge graph (FalkorDB) for facts and relationships extracted from synthesized neurons. Returns edges with temporal validity windows (valid_at / invalid_at). Requires FalkorDB running on localhost:6379.",
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
            "Busca neurônios do vault por similaridade semântica (HNSW cosine) "
            "ou full-text. Modo 'semantic' usa fastembed + índice HNSW; faz fallback "
            "automático para full-text se o índice estiver ausente ou desatualizado (>7d). "
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
            "Melhor para perguntas multi-hop que FTS5 não resolve. "
            "Retorna string bruta do LightRAG ou vazio se o índice não estiver disponível."
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
    "sinapse_temporal_search": lambda args: _temporal_search(args.get("query", "")),
    "sinapse_temporal_save": lambda args: _temporal_save(args.get("content", ""), args.get("kind", "change")),
    "sinapse_zettelkasten_split": lambda args: _zettelkasten_split(args.get("source_file", ""), args.get("output_dir", "cerebro/atoms")),
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
        import asyncio
        from core.lightrag_index import query_rag
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        result = loop.run_until_complete(query_rag(question, mode=mode))
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


def _zettelkasten_split(source_file, output_dir="cerebro/atoms"):
    """Split monolithic note into atomic Zettelkasten notes."""
    import importlib.util
    import os
    from pathlib import Path
    scripts_dir = os.path.dirname(__file__)
    zk_script = os.path.normpath(os.path.join(scripts_dir, "..", "knowledge", "sinapse-zettelkasten.py"))
    spec = importlib.util.spec_from_file_location("sinapse_zettelkasten", zk_script)
    zk_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(zk_mod)
    # Resolve source_file relative to project root if not absolute
    src = Path(source_file)
    if not src.is_absolute():
        project_root = Path(scripts_dir).resolve().parent.parent
        src = project_root / src
    src = src.resolve()
    if not src.exists():
        return {"error": f"Source file not found: {src}", "source_file": str(src)}
    # Resolve output_dir relative to project root if not absolute
    out = Path(output_dir)
    if not out.is_absolute():
        project_root = Path(scripts_dir).resolve().parent.parent
        out = project_root / out
    out = out.resolve()
    files = zk_mod.split_monolithic_file(str(src), str(out))
    return {"atoms_created": len(files), "files": files}


def _temporal_search(query):
    """Busca no claude-mem via API HTTP (FTS5 + Chroma)."""
    from urllib.request import Request, urlopen
    from urllib.error import URLError
    from urllib.parse import quote
    
    CLAUDE_MEM_URL = "http://127.0.0.1:37700"
    
    try:
        encoded = quote(query)
        req = Request(f"{CLAUDE_MEM_URL}/api/search?query={encoded}", method="GET")
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return {"source": "claude-mem (temporal)", "results": data, "query": query}
    except (URLError, json.JSONDecodeError, OSError) as e:
        return {"source": "claude-mem (temporal)", "error": str(e), "query": query}


def _temporal_save(content, kind="change"):
    """Salva observação no claude-mem (modo server-beta) ou fallback vault."""
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    CLAUDE_MEM_URL = "http://127.0.0.1:37700"

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
        vault_dir = Path(__file__).resolve().parent.parent.parent / "cerebro" / "cortex" / "frontal" / "trabalho" / "ativo"
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
            try:
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


if __name__ == "__main__":
    main()
