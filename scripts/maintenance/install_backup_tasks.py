"""Register backup maintenance tasks without PowerShell."""
from __future__ import annotations
import argparse, subprocess
from pathlib import Path

def specs(root: Path) -> tuple[tuple[str, str, str], ...]:
    python = root / '.venv' / 'Scripts' / 'python.exe'; script = root / 'scripts' / 'maintenance' / 'maintenance_tasks.py'
    return (
        ('Hive-Mind Backup Audit Daily', 'DAILY', f'"{python}" "{script}" --root "{root}" backup-audit'),
        ('Hive-Mind Backup Prune Weekly', 'WEEKLY', f'"{python}" "{script}" --root "{root}" backup-prune'),
    )
def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]); p.add_argument('--apply',action='store_true'); a=p.parse_args(argv); root=a.root.resolve()
    for name, schedule, command in specs(root):
        print(f'{name} -> {command}')
        if not a.apply: continue
        args=['/create','/tn',name,'/tr',command,'/sc',schedule,'/st','03:10' if schedule=='DAILY' else '03:30','/f']
        if schedule=='WEEKLY': args += ['/d','SUN']
        result=subprocess.run(['schtasks.exe',*args],text=True,capture_output=True,check=False)
        if result.returncode: raise SystemExit(result.stderr or result.stdout)
    return 0
if __name__=='__main__': raise SystemExit(main())
