#!/usr/bin/env python3
"""
Monitora eventos do Syncthing via polling de /rest/events e invoca
audit_memory.py --fix quando um arquivo .sync-conflict-* é detectado.

Requer SYNCTHING_API_KEY no .env. Sem a chave, o script recusa iniciar.
Degrada graciosamente se Syncthing estiver offline (ConnectionError ignorado).
"""
import os
import sys
import time
import subprocess
import requests
from pathlib import Path

# Carrega .env se python-dotenv disponível
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

SYNCTHING_URL = os.environ.get("SYNCTHING_URL", "http://127.0.0.1:8384")
SYNCTHING_API_KEY = os.environ.get("SYNCTHING_API_KEY", "")
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(Path(__file__).parent.parent))
POLL_INTERVAL = float(os.environ.get("SYNCTHING_POLL_INTERVAL", "30"))


def _headers() -> dict:
    return {"X-API-Key": SYNCTHING_API_KEY} if SYNCTHING_API_KEY else {}


def _trigger_audit() -> None:
    subprocess.run(
        [sys.executable, str(Path(SINAPSE_HOME) / "scripts" / "audit_memory.py"), "--fix"],
        check=False,
        timeout=120,
    )


def poll_once(last_event_id: int) -> int:
    """Faz uma requisição a /rest/events e processa eventos. Retorna o último ID visto."""
    r = requests.get(
        f"{SYNCTHING_URL}/rest/events",
        params={"since": last_event_id, "limit": 100, "timeout": int(POLL_INTERVAL - 5)},
        headers=_headers(),
        timeout=POLL_INTERVAL,
    )
    r.raise_for_status()
    for event in r.json():
        last_event_id = max(last_event_id, event.get("id", 0))
        if event.get("type") == "ItemFinished":
            item = event.get("data", {}).get("item", "")
            if ".sync-conflict-" in item:
                print(f"[syncthing_watcher] Conflito detectado: {item}", flush=True)
                _trigger_audit()
    return last_event_id


def run_loop() -> None:
    last_event_id = 0
    while True:
        try:
            last_event_id = poll_once(last_event_id)
        except requests.exceptions.ConnectionError:
            pass  # Syncthing offline — aguarda próximo ciclo
        except requests.exceptions.HTTPError as e:
            print(f"[syncthing_watcher] HTTP {e.response.status_code}", flush=True)
        except Exception as e:
            print(f"[syncthing_watcher] Erro: {e}", flush=True)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if not SYNCTHING_API_KEY:
        raise SystemExit(
            "SYNCTHING_API_KEY não configurada.\n"
            "Defina em .env: SYNCTHING_API_KEY=<chave da GUI do Syncthing>"
        )
    print(f"[syncthing_watcher] Iniciando — {SYNCTHING_URL}", flush=True)
    run_loop()
