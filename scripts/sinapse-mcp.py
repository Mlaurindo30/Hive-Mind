#!/usr/bin/env python3
"""
Sinapse Agent — MCP Server (stdio)
Expoe ferramentas de leitura e escrita do vault para qualquer agente MCP.

Uso:
  python3 scripts/sinapse-mcp.py

Config MCP do agente:
  {
    "mcpServers": {
      "sinapse-memory": {
        "command": "python3",
        "args": ["scripts/sinapse-mcp.py"],
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
    _plugin_path = Path(__file__).resolve().parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
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
    }
]

HANDLERS = {
    "sinapse_query": lambda args: sm._query_vault_knowledge(args.get("query", "")) or {},
    "sinapse_save_decision": lambda args: {
        "saved": sm._save_decision(args.get("title", ""), args.get("content", "")) is not None
    },
    "sinapse_save_learning": lambda args: {
        "saved": sm._save_learning(args.get("title", ""), args.get("content", "")) is not None
    },
    "sinapse_health": lambda args: sm.health_check(),
    "sinapse_session_end": lambda args: _session_end(args.get("summary", "")),
}


def _session_end(summary):
    sm._session_decisions = []
    sm._session_learnings = []
    sm._update_current_state([], [], summary)
    return {"updated": True}


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
