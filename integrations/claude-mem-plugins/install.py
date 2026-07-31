"""Install the bundled Claude Mem plugin into a selected agent directory."""
from __future__ import annotations
import argparse, os, shutil
from pathlib import Path
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--target',type=Path,default=Path(os.environ.get('USERPROFILE',Path.home()))/'.gemini/antigravity-cli/plugins/claude-mem'); a=p.parse_args(argv); source=Path(__file__).resolve().parent
 a.target.mkdir(parents=True,exist_ok=True)
 for item in source.iterdir():
  if item.name == Path(__file__).name: continue
  dest=a.target/item.name
  if item.is_dir(): shutil.copytree(item,dest,dirs_exist_ok=True)
  else: shutil.copy2(item,dest)
 print(f'claude-mem plugin installed to {a.target}'); return 0
if __name__=='__main__': raise SystemExit(main())
