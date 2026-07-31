"""Windows vault ACL enforcement without a PowerShell runtime dependency."""
from __future__ import annotations
import argparse, ctypes, os, secrets, string, subprocess
from pathlib import Path

def _admin() -> bool:
    try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except AttributeError: return False
def _run(*args: str) -> None:
    result=subprocess.run(args,text=True,encoding='mbcs',errors='replace',capture_output=True,check=False)
    if result.returncode: raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'command failed')
def _service_user() -> str: return os.environ.get('HIVE_SERVICE_USER','hive-dreamer')
def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]); g=p.add_mutually_exclusive_group(); g.add_argument('--status',action='store_true'); g.add_argument('--revert',action='store_true'); a=p.parse_args(argv); root=a.root.resolve(); vault=root/'cerebro'; intake=vault/'90-intake'; service=_service_user(); human=os.environ.get('USERNAME','')
    if not vault.is_dir(): raise SystemExit(f'Vault not found at {vault}')
    if a.status:
        print(f'Vault: {vault}'); print(f'Intake: {intake} ({"present" if intake.exists() else "missing"})'); result=subprocess.run(['net.exe','user',service],text=True,encoding='mbcs',errors='replace',capture_output=True,check=False); print(f'Service user: {service if result.returncode==0 else "not created"}'); print(subprocess.run(['icacls.exe',str(vault)],text=True,encoding='mbcs',errors='replace',capture_output=True,check=False).stdout or ''); return 0
    if not _admin(): raise SystemExit('This command must run in an elevated Administrator terminal.')
    if a.revert:
        _run('icacls.exe',str(vault),'/reset','/T','/C'); _run('icacls.exe',str(vault),'/setowner',human,'/T','/C'); print(f'OK enforcement reverted; service account {service} was retained.'); return 0
    if subprocess.run(['net.exe','user',service],capture_output=True,check=False).returncode:
        alphabet=string.ascii_letters+string.digits+'!@#$%'; password=''.join(secrets.choice(alphabet) for _ in range(28)); _run('net.exe','user',service,password,'/add','/expires:never','/passwordchg:no')
    intake.mkdir(parents=True,exist_ok=True)
    for args in (('/inheritance:r','/T','/C'),('/setowner',service,'/T','/C'),('/grant',f'{service}:(OI)(CI)F','/T','/C'),('/grant',f'{human}:(OI)(CI)M','/T','/C'),('/grant','SYSTEM:(OI)(CI)F','/T','/C')): _run('icacls.exe',str(vault),*args)
    _run('icacls.exe',str(intake),'/grant','*S-1-5-11:(OI)(CI)M','/C'); print(f'OK vault owned by {service}; intake is writable by authenticated users.'); return 0
if __name__=='__main__': raise SystemExit(main())
