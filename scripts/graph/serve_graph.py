"""Serve the validated Graphify graph."""
from __future__ import annotations
import argparse, subprocess
from pathlib import Path
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]); p.add_argument('--port',type=int,default=8000); a=p.parse_args(argv); g=a.root.resolve()/'cerebro/cortex/occipital/grafo/graph.json'
 if not g.is_file(): raise SystemExit(f'Graph not found at {g}. Run scripts/graph/build_graph.py first.')
 return subprocess.run([str(a.root.resolve()/'.venv/Scripts/python.exe'),'-m','graphify.serve','--graph',str(g),'--port',str(a.port)],check=False).returncode
if __name__=='__main__': raise SystemExit(main())
