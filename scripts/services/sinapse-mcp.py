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

TOOLS = [
    {
        "name": "sinapse_query",
        "description": "Search the Sinapse vault across all memory backends (NeuralMemory associative, claude-mem semantic/Chroma, Graphify structural/Leiden clustering). Returns nodes, edges, and observations from the knowledge graph and temporal memory.",
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
        "description": "Health check of all Sinapse backends (NeuralMemory, claude-mem, Graphify, RTK) and vault status. Returns node count and backend availability.",
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
        "description": "Capture the user's screen and save it to the vault (cerebro/inbox/visual/). Returns the absolute path of the image and the provided description. Useful for visual context and UI review.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Optional description/reason for the capture. Will be used in the filename."
                }
            }
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
    }
]

HANDLERS = {
    "sinapse_query": lambda args: sm._backend_umc(args.get("query", "")) or {"source": "umc", "observations": [], "query": args.get("query")},
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
    "sinapse_capture_screen": lambda args: _capture_screen(args.get("description", "")),
    "sinapse_plan_goal": lambda args: _plan_goal(args.get("goal", ""), args.get("context")),
    "search_memories": lambda args: _search_memories(
        args.get("query", ""),
        top_k=int(args.get("top_k", 10)),
        project=args.get("project"),
        mode=args.get("mode", "semantic"),
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


def _capture_screen(description=""):
    """Captura tela via Screenpipe REST (primário) ou visual_capture.py (fallback)."""
    import os
    import subprocess

    # Tenta Screenpipe primeiro (zero overhead se não estiver rodando)
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts.capture.parsers.screenpipe import screenpipe_alive, capture_screenshot
        if screenpipe_alive():
            result = capture_screenshot(description)
            if result.get("path"):
                return {"success": True, **result}
    except Exception:
        pass

    # Fallback: visual_capture.py via subprocess
    scripts_dir = os.path.dirname(__file__)
    capture_script = os.path.join(scripts_dir, "visual_capture.py")
    cmd = [sys.executable, capture_script]
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
    import importlib.util
    import os
    scripts_dir = os.path.dirname(__file__)
    zk_script = os.path.join(scripts_dir, "sinapse-zettelkasten.py")
    spec = importlib.util.spec_from_file_location("sinapse_zettelkasten", zk_script)
    zk_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(zk_mod)
    files = zk_mod.split_monolithic_file(source_file, output_dir)
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
    """Decompõe objetivo em passos via planner e persiste no Intent Memory."""
    import importlib.util
    import os
    scripts_dir = os.path.dirname(__file__)
    planner_path = os.path.join(scripts_dir, "planner.py")
    spec = importlib.util.spec_from_file_location("planner", planner_path)
    planner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(planner)

    steps = planner.decompose_goal(goal, context)
    goal_id = planner.save_goal(goal, steps)
    return {"goal_id": goal_id, "steps": steps}


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
                "serverInfo": {"name": "sinapse-memory", "version": "1.0.0"}
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
