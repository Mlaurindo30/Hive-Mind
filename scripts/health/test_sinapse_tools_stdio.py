#!/usr/bin/env python3
"""
test_sinapse_tools_stdio.py — Testa as 15 tools do sinapse-mcp via stdio JSON-RPC.
Abordagem: um processo por tool (spawn → request → EOF). Funciona porque o
servidor responde por linha e o subprocess captura a saída até EOF.

Uso:
    python3 scripts/health/test_sinapse_tools_stdio.py [--all] [--tool NOME]
"""
import json
import os
import subprocess
import sys
import time

MCP_CMD = [sys.executable, "scripts/services/sinapse-mcp.py"]

# ---- helpers ----
def mcp_request(tool_name, arguments=None, timeout=15):
    req = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments or {}},
        "id": 1,
    }
    try:
        result = subprocess.run(
            MCP_CMD,
            input=(json.dumps(req) + "\n").encode("utf-8"),
            capture_output=True,
            timeout=timeout,
        )
        out = result.stdout.decode(errors="replace").strip()
        if not out:
            return {"error": {"message": "stdout vazio", "stderr": result.stderr.decode(errors="replace")[:300]}}
        for line in reversed(out.split("\n")):
            try:
                msg = json.loads(line)
                if "result" in msg or "error" in msg:
                    return msg
            except json.JSONDecodeError:
                continue
        return {"error": {"message": "nenhuma resposta JSON válida", "raw": out[:300]}}
    except subprocess.TimeoutExpired:
        return {"error": {"message": f"timeout {timeout}s"}}
    except Exception as e:
        return {"error": {"message": str(e)}}

def tool_text(r):
    if "error" in r:
        return f"ERROR: {r['error']}"
    return "\n".join(c.get("text","") for c in r.get("result",{}).get("content",[]) if c.get("type")=="text") or "(vazio)"

def is_ok(r, txt=""):
    if "error" in r:
        return False
    txt = txt or tool_text(r).lower()
    if "erro" in txt or "error" in txt:
        return False
    return True

# ---- 15 testes ----
TESTS = [
    ("sinapse_health",                lambda: mcp_request("sinapse_health")),
    ("sinapse_query",                 lambda: mcp_request("sinapse_query", {"query": "teste MCP stdio"})),
    ("sinapse_temporal_search",       lambda: mcp_request("sinapse_temporal_search", {"query": "teste"})),
    ("sinapse_temporal_timeline",     lambda: mcp_request("sinapse_temporal_timeline", {"query": "teste", "depth_before": 1, "depth_after": 1})),
    ("sinapse_temporal_get_observations", lambda: mcp_request("sinapse_temporal_get_observations", {"ids": [1]})),
    ("sinapse_temporal_graph_search", lambda: mcp_request("sinapse_temporal_graph_search", {"query": "arquitetura", "num_results": 3})),
    ("search_memories",               lambda: mcp_request("search_memories", {"query": "teste", "top_k": 3, "mode": "text"})),
    ("sinapse_save_decision",         lambda: mcp_request("sinapse_save_decision", {"title": "[TESTE MCP] Decisão stdio", "content": "teste de conexão"})),
    ("sinapse_save_learning",         lambda: mcp_request("sinapse_save_learning", {"title": "[TESTE MCP] Aprendizado stdio", "content": "teste de conexão"})),
    ("sinapse_plan_goal",             lambda: mcp_request("sinapse_plan_goal", {"goal": "Validar 15 tools Sinapse via stdio"})),
    ("sinapse_zettelkasten_split",    lambda: mcp_request("sinapse_zettelkasten_split", {"source_file": "cerebro/cerebelo/padroes/Patterns.md", "output_dir": "cerebro/cortex/temporal/Hive-Mind/atoms/test_stdio"}, timeout=60)),
    ("sinapse_capture_screen",        lambda: mcp_request("sinapse_capture_screen", {"description": "teste mcp stdio", "monitor": 3})),
    ("sinapse_temporal_save",         lambda: mcp_request("sinapse_temporal_save", {"content": "[TESTE MCP] obs stdio", "kind": "event"})),
    ("sinapse_session_end",           lambda: mcp_request("sinapse_session_end", {"summary": "teste MCP stdio"})),
]

# ---- main ----
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--tool")
    args = ap.parse_args()

    if args.tool:
        run = [args.tool]
    elif args.all:
        run = [n for n, _ in TESTS]
    else:
        run = ["sinapse_health"]

    print("=== Testando sinapse-mcp.py (stdio, um processo por tool) ===\n")
    results = []
    for i, name in enumerate(run, 1):
        fn = dict(TESTS)[name]
        t0 = time.monotonic()
        r = fn()
        elapsed = time.monotonic() - t0
        txt = tool_text(r)
        ok = is_ok(r, txt)
        results.append((name, ok, elapsed, txt))
        tag = "✅" if ok else "❌"
        print(f"  [{i}/{len(run)}] {tag} {name:<40} {elapsed:.1f}s")
        for ln in txt.split("\n")[:5]:
            print(f"       {ln}")

    ok_n = sum(1 for _, ok, _, _ in results if ok)
    print(f"\n{'='*60}")
    print(f"  {ok_n}/{len(results)} OK | {len(results)-ok_n} falhas")
    if args.all:
        print(f"{'='*60}")
        for name, ok, et, _ in results:
            print(f"  {'✅' if ok else '❌'} {name:<40} {et:.1f}s")
