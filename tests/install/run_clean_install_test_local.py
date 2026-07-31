"""Execute a non-interactive local installation through the Python entrypoint."""
from __future__ import annotations
import argparse, subprocess
from pathlib import Path
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]); p.add_argument('--with-tests',action='store_true'); a=p.parse_args(argv); root=a.root.resolve(); command=[str(root/'.venv/Scripts/python.exe'),str(root/'scripts/setup/windows_install_entry.py'),'--root',str(root),'--non-interactive']+(['--with-tests'] if a.with_tests else [])
 return subprocess.run(command,cwd=root,check=False).returncode
if __name__=='__main__': raise SystemExit(main())
