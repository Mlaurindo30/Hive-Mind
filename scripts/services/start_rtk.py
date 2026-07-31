"""Run RTK initialization through a portable Python entrypoint."""
from __future__ import annotations
import argparse, shutil, subprocess
from pathlib import Path
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]); g=p.add_mutually_exclusive_group(); g.add_argument('--only'); g.add_argument('--all',action='store_true'); p.add_argument('arguments',nargs='*'); a=p.parse_args(argv); root=a.root.resolve(); rtk=root/'integrations/rtk/target/release/rtk.exe'; exe=str(rtk) if rtk.is_file() else shutil.which('rtk')
 if not exe: raise SystemExit('rtk was not found. Run the Python installer after integrations are bootstrapped.')
 command=['init']+(['--all'] if a.all else (['--only',a.only] if a.only else []))+a.arguments
 return subprocess.run([exe,*command],check=False).returncode
if __name__=='__main__': raise SystemExit(main())
