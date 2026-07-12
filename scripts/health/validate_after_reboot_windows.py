#!/usr/bin/env python3
"""Windows post-reboot validation; never depends on systemd or procfs."""
from __future__ import annotations
import json, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'logs'/'post-reboot-validation.json'
def task_exists(name: str) -> bool:
    return subprocess.run(['schtasks','/Query','/TN',name],capture_output=True,text=True).returncode == 0
def load_state(timeout: int = 120) -> dict:
    path=ROOT/'logs'/'supervisor'/'state.json'; deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            state=json.loads(path.read_text())
            if state: return state
        except Exception: pass
        time.sleep(2)
    return {}
def main() -> int:
    state=load_state()
    checks={'scheduled_supervisor':task_exists('HiveMind-Supervisor'),'supervisor_state_present':bool(state),'services_healthy':bool(state) and all(v.get('state')=='healthy' for v in state.values())}
    report={'platform':'windows','validated_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'services':state,'status':'pass' if all(checks.values()) else 'fail'}
    REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['status']=='pass' else 1
if __name__ == '__main__': raise SystemExit(main())