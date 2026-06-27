#!/usr/bin/env python3
"""
Sinapse Agent — CLI standalone de escrita para agentes sem plugin Python.
Uso:
  python3 scripts/services/sinapse-write.py decision --title "Título" --content "Conteúdo"
  python3 scripts/services/sinapse-write.py learning --title "Título" --content "Conteúdo"
  python3 scripts/services/sinapse-write.py query "texto da busca"
  python3 scripts/services/sinapse-write.py health
  python3 scripts/services/sinapse-write.py session-end --summary "Resumo da sessão"
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import paths as cp
from plugins.hermes import sinapse_memory as _sinapse_memory_adapter  # noqa: F401
from scripts.knowledge.sinapse_zettelkasten import split_monolithic_file
import sinapse_memory as sm

DEFAULT_ZETTEL_DIR = str(cp.TEMPORAL / "Hive-Mind" / "atoms")


def main():
    parser = argparse.ArgumentParser(description="Sinapse Agent — write CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("decision", help="Save a decision to the vault")
    d.add_argument("--title", required=True, help="Decision title")
    d.add_argument("--content", required=True, help="Decision content")
    d.add_argument("--dry-run", action="store_true", default=False, help="Preview without writing files or persisting to DB")

    l = sub.add_parser("learning", help="Save a learning to Patterns.md")
    l.add_argument("--title", required=True, help="Learning title")
    l.add_argument("--content", required=True, help="Learning content")
    l.add_argument("--dry-run", action="store_true", default=False, help="Preview without writing files or persisting to DB")

    q = sub.add_parser("query", help="Query vault knowledge across all backends")
    q.add_argument("text", help="Search query")

    sub.add_parser("health", help="Health check of all backends")

    se = sub.add_parser("session-end", help="End session and update Current State")
    se.add_argument("--summary", required=True, help="Session summary")

    zk = sub.add_parser("zettelkasten", help="Auto-partition monolithic file into atomic Zettelkasten notes")
    zk.add_argument("--source", required=True, help="Monolithic markdown file path")
    zk.add_argument("--output-dir", default=DEFAULT_ZETTEL_DIR, help="Target atoms directory")

    obs = sub.add_parser("observation", help="Save a generic observation to the UMC")
    obs.add_argument("--title", required=True, help="Observation title")
    obs.add_argument("--content", required=True, help="Observation content")
    obs.add_argument("--kind", default="event", help="Observation kind (event, execution, etc.)")

    args = parser.parse_args()

    if args.command == "decision":
        sm.DRY_RUN = args.dry_run
        result = sm._save_decision(args.title, args.content)
        print(json.dumps({"saved": result is not None, "path": result or None, "dry_run": args.dry_run}))
    elif args.command == "learning":
        sm.DRY_RUN = args.dry_run
        result = sm._save_learning(args.title, args.content)
        print(json.dumps({"saved": result is not None, "path": result or None, "dry_run": args.dry_run}))
    elif args.command == "observation":
        result = sm._umc_save_observation(args.title, args.content, obs_type=args.kind)
        print(json.dumps({"saved": result}))
    elif args.command == "query":
        result = sm._query_vault_knowledge(args.text)
        print(json.dumps(result or {}, default=str, indent=2))
    elif args.command == "health":
        result = sm.health_check()
        print(json.dumps(result, default=str, indent=2))
    elif args.command == "session-end":
        # Captura o buffer da sessão ANTES de zerar — senão as decisões/aprendizados
        # acumulados nunca chegam ao Current State (A3/P1-9)
        decisions = list(sm._session_decisions)
        learnings = list(sm._session_learnings)
        sm._session_decisions.clear()
        sm._session_learnings.clear()
        sm._update_current_state(decisions, learnings, args.summary)
        print(json.dumps({"updated": True}))
    elif args.command == "zettelkasten":
        files = split_monolithic_file(args.source, args.output_dir)
        print(json.dumps({"atoms_created": len(files), "files": files}, indent=2))


if __name__ == "__main__":
    main()
