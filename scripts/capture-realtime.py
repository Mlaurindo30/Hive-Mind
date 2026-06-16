#!/usr/bin/env python3
"""
capture-realtime.py — Daemon de captura em TEMPO REAL via inotify (zero deps).

Orquestrador fino: motor de transporte em capture_core, ferramentas em
capture_adapters. Dono das fontes owner=="realtime". Modelo UNIFICADO: vigia os
dirs de cada ferramenta; a QUALQUER mudança (ms), re-parseia as fontes daquela
ferramenta (parser DEDICADO) e ingere via core.ingest(). A idempotência por
CONTENT-HASH garante que só conteúdo NOVO emite — independe do formato (append,
reescrita, array, SQLite). Estado ISOLADO por ferramenta; dono ÚNICO (o tailer
não toca nas fontes owner=="realtime").
"""
from __future__ import annotations

import ctypes
import glob
import os
import select
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_core as core                       # noqa: E402
from capture_adapters import adapters_by_owner    # noqa: E402

ADAPTERS = adapters_by_owner("realtime")

WINDOW_S = 2 * 3600          # só sessões ativas nesta janela (DBs multi-sessão)
LIVE_MAX_AGE_S = 120.0       # em evento ao vivo, só re-parseia fontes recém-tocadas

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
IN_MODIFY = 0x2; IN_CLOSE_WRITE = 0x8; IN_MOVED_TO = 0x80; IN_CREATE = 0x100
MASK = IN_MODIFY | IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE
_HDR = struct.calcsize("iIII")

def ingest_platform(plat: str, states: dict, max_age: float = LIVE_MAX_AGE_S) -> int:
    """Re-parseia as fontes da plataforma (parser dedicado) e ingere. Só parseia
    arquivos modificados nos últimos `max_age` s (pula fontes ociosas).

    SEM debounce de borda-de-subida: rodar IMEDIATAMENTE no evento preserva o
    realtime de ms (ex.: copilot, como era antes). A tempestade de eventos do
    WAL/SQLite de UMA escrita já é coalescida no event-loop (todos os eventos de
    um os.read viram 1 só `touched`/parse), e o re-parse é idempotente
    (content-hash) — então não há perda nem flood."""
    now = time.time()
    core.SESSION_CUTOFF_MS = int((now - WINDOW_S) * 1000)
    adp = ADAPTERS[plat]
    parser = adp["parser"]
    st = states[plat]
    cutoff_mtime = now - max_age
    sent = 0
    for pattern in adp["sources"]:
        for src in glob.glob(pattern):
            p = Path(src)
            if not p.is_file() or core._src_mtime(p) < cutoff_mtime:
                continue
            try:
                for sess in parser(p):
                    sent += core.ingest(plat, sess, st)
            except Exception as exc:
                print(f"  ⚠ {plat}: {exc}", flush=True)
    if sent:
        core.save_state(plat, st)
    return sent


def main() -> int:
    while not core.worker_alive():
        print(f"aguardando worker em {core.BASE}...", flush=True)
        time.sleep(3)
    fd = _libc.inotify_init1(os.O_NONBLOCK)
    if fd < 0:
        print("inotify_init1 falhou", file=sys.stderr)
        return 1
    wd_plat: dict[int, str] = {}
    watched: set[str] = set()
    states = {plat: core.load_state(plat) for plat in ADAPTERS}

    def refresh():
        for plat, adp in ADAPTERS.items():
            for pattern in adp.get("watch", []):
                for d in glob.glob(pattern):
                    if d in watched or not os.path.isdir(d):
                        continue
                    wd = _libc.inotify_add_watch(fd, d.encode(), MASK)
                    if wd >= 0:
                        wd_plat[wd] = plat
                        watched.add(d)
                        print(f"  👁 {plat} [{adp['mode']}]: {d}", flush=True)

    refresh()
    for plat in ADAPTERS:                 # catch-up histórico no startup
        n = ingest_platform(plat, states, max_age=WINDOW_S)
        if n:
            print(f"  🔄 {plat} catch-up: {n} turn(s)", flush=True)
    last_refresh = time.time()
    print("capture-realtime ativo (inotify, modelo unificado por content-hash).", flush=True)

    while True:
        r, _, _ = select.select([fd], [], [], 5.0)
        now = time.time()
        if r:
            try:
                buf = os.read(fd, 65536)
            except BlockingIOError:
                buf = b""
            i = 0
            touched: set[str] = set()
            while i + _HDR <= len(buf):
                wd, mask, cookie, nlen = struct.unpack_from("iIII", buf, i)
                i += _HDR + nlen
                plat = wd_plat.get(wd)
                if plat:
                    touched.add(plat)
            for plat in touched:
                n = ingest_platform(plat, states)
                if n:
                    print(f"  ⚡ {plat} → {n} turn(s) novo(s)", flush=True)
        if now - last_refresh > 15:
            refresh()
            last_refresh = now


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
