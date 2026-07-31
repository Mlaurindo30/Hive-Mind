"""Python entrypoints for scheduled Hive-Mind maintenance on Windows."""
from __future__ import annotations
import argparse, subprocess
from datetime import datetime
from pathlib import Path

def _root(value: str | None) -> Path: return Path(value).resolve() if value else Path(__file__).resolve().parents[2]
def _run_audit(root: Path, *, apply: bool, directory: str, retention: int) -> int:
 log_dir=root/'logs'/directory; log_dir.mkdir(parents=True,exist_ok=True); output=log_dir/f"{'prune' if apply else 'audit'}-{datetime.now():%Y-%m-%d-%H%M%S}.json"; command=[str(root/'.venv/Scripts/python.exe'),str(root/'scripts/health/backup_audit.py'),'--json']+(['--apply'] if apply else [])
 result=subprocess.run(command,cwd=root,capture_output=True,text=True,check=False); output.write_text(result.stdout,encoding='utf-8'); cutoff=datetime.now().timestamp()-retention*86400
 for stale in log_dir.glob('*.json'):
  if stale.stat().st_mtime < cutoff: stale.unlink()
 print(output); return result.returncode
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--root'); sub=p.add_subparsers(dest='command',required=True); sub.add_parser('backup-audit'); prune=sub.add_parser('backup-prune'); prune.add_argument('--dry-run',action='store_true'); sync=sub.add_parser('sync-diario'); update=sub.add_parser('integrations-update'); update.add_argument('--skip-uv',action='store_true'); update.add_argument('--skip-claude-plugin',action='store_true'); a=p.parse_args(argv); root=_root(a.root)
 if a.command=='backup-audit': return _run_audit(root,apply=False,directory='backup-audit',retention=60)
 if a.command=='backup-prune': return _run_audit(root,apply=not a.dry_run,directory='backup-prune',retention=182)
 if a.command=='sync-diario':
  log=root/'logs/sync-diario'; log.mkdir(parents=True,exist_ok=True); out=log/f'sync-{datetime.now():%Y-%m-%d-%H%M%S}.log'; r=subprocess.run([str(root/'.venv/Scripts/python.exe'),str(root/'scripts/graph/build_graph.py'),'--root',str(root),'--force'],cwd=root,capture_output=True,text=True,check=False); out.write_text(r.stdout+r.stderr,encoding='utf-8'); print(out); return r.returncode
 for command in ([str(root/'.venv/Scripts/python.exe'),str(root/'scripts/setup/components.py'),'update'],[str(root/'.venv/Scripts/python.exe'),str(root/'scripts/setup/components.py'),'verify']): subprocess.run(command,cwd=root,check=True)
 if not a.skip_uv:
  subprocess.run(['uv','lock','--upgrade'],cwd=root,check=True); subprocess.run(['uv','sync','--frozen','--all-groups'],cwd=root,check=True)
 subprocess.run([str(root/'.venv/Scripts/python.exe'),str(root/'scripts/setup/verify_wrappers.py')],cwd=root,check=True)
 if not a.skip_claude_plugin and __import__('shutil').which('claude'): return subprocess.run(['claude','plugins','update','claude-mem@thedotmack'],cwd=root,check=False).returncode
 return 0
if __name__=='__main__': raise SystemExit(main())
