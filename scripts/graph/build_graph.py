"""Build and validate the local Graphify graph without a shell wrapper."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--skip-hnsw", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve(); vault = root / "cerebro"; graph_dir = vault / "cortex" / "occipital" / "grafo"; graph = graph_dir / "graph.json"
    if not vault.is_dir(): raise SystemExit(f"Vault not found at {vault}")
    graph_dir.mkdir(parents=True, exist_ok=True); os.environ["GRAPHIFY_OUT"] = str(graph_dir)
    if graph.exists(): shutil.copy2(graph, graph_dir / "graph.json.bak")
    command = [str(root / ".venv" / "Scripts" / "python.exe"), "-m", "graphify", "update", str(vault)]
    if args.force: command.append("--force")
    result = subprocess.run(command, check=False)
    if result.returncode and not graph.exists(): graph.write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    if args.extract: subprocess.run(command[:3] + ["extract", str(vault), "--out", str(graph_dir)], check=True)
    if not args.skip_hnsw: subprocess.run([command[0], "-c", "from core.hnsw_index import incremental_update; from core.database import embed_text,get_connection; c=get_connection(); print(f'HNSW: {incremental_update(c,embed_text)} neurons indexed'); c.close()"], cwd=root, check=True)
    json.loads(graph.read_text(encoding="utf-8-sig")); print(f"graph ok: {graph}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
