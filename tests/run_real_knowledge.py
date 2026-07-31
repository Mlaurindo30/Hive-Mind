"""Run opt-in real-backend knowledge tests."""
from __future__ import annotations
import argparse, subprocess
from pathlib import Path
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]); p.add_argument('--report',default='logs/real-knowledge-report.xml'); a=p.parse_args(argv); root=a.root.resolve(); report=root/a.report; report.parent.mkdir(parents=True,exist_ok=True)
 return subprocess.run([str(root/'.venv/Scripts/python.exe'),'-m','pytest','tests/real','-m','real','-v','--timeout=1200',f'--junitxml={report}'],cwd=root,check=False).returncode
if __name__=='__main__': raise SystemExit(main())
