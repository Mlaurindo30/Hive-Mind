"""Run the portable Hive-Mind verification suite."""
from __future__ import annotations
import argparse, subprocess
from pathlib import Path
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]); p.add_argument('--skip-integration',action='store_true'); p.add_argument('--skip-e2e',action='store_true'); a=p.parse_args(argv); root=a.root.resolve(); python=root/'.venv/Scripts/python.exe'
 commands=[[str(python),str(root/'tests/smoke/test_smoke.py'),'--root',str(root)],[str(python),'-m','pytest','tests/unit/','-v']]
 if not a.skip_integration: commands.append([str(python),'-m','pytest','tests/integration/','-v'])
 if not a.skip_e2e: commands.append([str(python),'-m','pytest','tests/e2e/','-v'])
 for command in commands:
  if subprocess.run(command,cwd=root,check=False).returncode: return 1
 return 0
if __name__=='__main__': raise SystemExit(main())
