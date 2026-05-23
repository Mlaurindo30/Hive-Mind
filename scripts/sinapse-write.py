#!/usr/bin/env python3
"""
Sinapse Agent — CLI standalone de escrita para agentes sem plugin Python.
Uso:
  python3 scripts/sinapse-write.py decision --title "Título" --content "Conteúdo"
  python3 scripts/sinapse-write.py learning --title "Título" --content "Conteúdo"
  python3 scripts/sinapse-write.py query "texto da busca"
  python3 scripts/sinapse-write.py health
  python3 scripts/sinapse-write.py session-end --summary "Resumo da sessão"
"""

import argparse
import json
import os
import sys
from pathlib import Path
import importlib.util

if "sinapse_memory" not in sys.modules:
    _plugin_path = Path(__file__).resolve().parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
    spec = importlib.util.spec_from_file_location("sinapse_memory", _plugin_path)
    sm = importlib.util.module_from_spec(spec)
    sys.modules["sinapse_memory"] = sm
    spec.loader.exec_module(sm)
else:
    import sinapse_memory as sm


def main():
    parser = argparse.ArgumentParser(description="Sinapse Agent — write CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("decision", help="Save a decision to the vault")
    d.add_argument("--title", required=True, help="Decision title")
    d.add_argument("--content", required=True, help="Decision content")

    l = sub.add_parser("learning", help="Save a learning to Patterns.md")
    l.add_argument("--title", required=True, help="Learning title")
    l.add_argument("--content", required=True, help="Learning content")

    q = sub.add_parser("query", help="Query vault knowledge across all backends")
    q.add_argument("text", help="Search query")

    sub.add_parser("health", help="Health check of all backends")

    se = sub.add_parser("session-end", help="End session and update Current State")
    se.add_argument("--summary", required=True, help="Session summary")

    args = parser.parse_args()

    if args.command == "decision":
        result = sm._save_decision(args.title, args.content)
        print(json.dumps({"saved": result is not None, "path": result or None}))
    elif args.command == "learning":
        result = sm._save_learning(args.title, args.content)
        print(json.dumps({"saved": result is not None, "path": result or None}))
    elif args.command == "query":
        result = sm._query_vault_knowledge(args.text)
        print(json.dumps(result or {}, default=str, indent=2))
    elif args.command == "health":
        result = sm.health_check()
        print(json.dumps(result, default=str, indent=2))
    elif args.command == "session-end":
        sm._session_decisions = []
        sm._session_learnings = []
        sm._update_current_state([], [], args.summary)
        print(json.dumps({"updated": True}))


if __name__ == "__main__":
    main()
