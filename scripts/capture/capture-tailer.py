#!/usr/bin/env python3
"""
capture-tailer.py — Ingestor PERIÓDICO (systemd timer) das fontes de owner=="timer".

Orquestrador fino: importa o motor de transporte (capture_core) e o registro de
ferramentas (capture_adapters). Cada ferramenta tem seu parser DEDICADO e seu
estado ISOLADO. Este processo é dono SÓ das fontes de baixa frequência/CLI
(mimo, openclaw, gemini-cli). As de owner=="realtime" são exclusivas do daemon
capture-realtime — nunca há dois donos para a mesma fonte.

Uso:
  capture-tailer.py --all --scan --since-hours 1      # todas as fontes do timer
  capture-tailer.py --platform mimo --source <db>     # uma fonte específica
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_core as core                       # noqa: E402
from capture_adapters import ADAPTERS, adapters_by_owner  # noqa: E402


def _acquire_lock():
    """Garante instância única do timer (evita corrida no state-file quando o timer
    dispara enquanto uma execução anterior ainda roda)."""
    import fcntl as _fcntl
    lock_path = core.DATA_DIR / "tailer.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fh = open(lock_path, "r+")
    except FileNotFoundError:
        fh = open(lock_path, "w")
    try:
        _fcntl.flock(fh, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            fh.seek(0)
            stale_pid = int(fh.read().strip() or 0)
        except (ValueError, OSError):
            stale_pid = 0
        if stale_pid > 1:
            try:
                os.kill(stale_pid, 0)
            except OSError:
                fh.close()
                fh = open(lock_path, "w")
                _fcntl.flock(fh, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                print(f"  🔓 lock órfão do PID {stale_pid} liberado")
            else:
                print(f"⊘ outra instância do tailer já roda (PID {stale_pid}) — saindo.")
                sys.exit(0)
        else:
            print("⊘ outra instância do tailer já roda — saindo.")
            sys.exit(0)
    fh.seek(0)
    fh.write(str(os.getpid()))
    fh.truncate()
    fh.flush()
    return fh


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=list(ADAPTERS),
                    help="plataforma específica; omita com --all")
    ap.add_argument("--all", action="store_true", help="todas as fontes do timer")
    ap.add_argument("--source")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--since-hours", type=float, default=24.0,
                    help="no --scan, só fontes modificadas nas últimas N horas")
    args = ap.parse_args()
    if not args.all and not args.platform:
        ap.error("informe --platform <p> ou --all")
    if not core.worker_alive():
        print(f"⊘ worker fora em {core.BASE} — pulando (próxima execução recupera)")
        return 0

    _lock = _acquire_lock()  # mantém o FD vivo enquanto o processo roda

    cutoff = time.time() - args.since_hours * 3600
    core.SESSION_CUTOFF_MS = int(cutoff * 1000)
    # DONO ÚNICO: --all processa só owner=="timer". Realtime é do daemon.
    platforms = list(adapters_by_owner("timer")) if args.all else [args.platform]
    total = 0

    for plat in platforms:
        adp = ADAPTERS[plat]
        parser = adp["parser"]
        if args.source and not args.all:
            sources = [Path(args.source)]
        else:
            found = []
            for pattern in adp["sources"]:
                found.extend(glob.glob(pattern))
            sources = [Path(p) for p in found
                       if Path(p).is_file() and core._src_mtime(Path(p)) >= cutoff]
        if not sources:
            continue
        st = core.load_state(plat)        # estado ISOLADO desta plataforma
        for s in sources:
            if not s.is_file():
                continue
            try:
                sessions = parser(s)
            except Exception as exc:
                print(f"  ⚠ {plat}:{s.name}: parse falhou ({exc})")
                continue
            for sess in sessions:
                total += core.ingest(plat, sess, st)
        core.save_state(plat, st)         # salva só o arquivo desta plataforma
    print(f"total: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
