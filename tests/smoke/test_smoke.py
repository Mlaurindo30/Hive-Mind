"""Portable smoke checks for a prepared Hive-Mind workspace."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]); a=p.parse_args(argv); root=a.root.resolve(); checks={'python':(root/'.venv/Scripts/python.exe').is_file(),'project root':(root/'pyproject.toml').is_file(),'env file':(root/'.env').is_file(),'vault':(root/'cerebro').is_dir(),'UMC database':(root/'hive_mind.db').is_file()}; failed=[name for name,ok in checks.items() if not ok]
 for name,ok in checks.items(): print(f'[{"ok" if ok else "fail"}] {name}')
 if failed: print('missing: '+', '.join(failed),file=sys.stderr); return 1
 print('smoke ok'); return 0
if __name__=='__main__': raise SystemExit(main())
