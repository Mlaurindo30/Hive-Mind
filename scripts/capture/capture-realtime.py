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


def _dir_has_recent_source(directory: str, cutoff_mtime: float, max_files: int = 128) -> bool:
    """True if a watched directory contains a recently modified source file.

    Append-only tools (Codex) and rewritten transcript tools (Antigravity/Kimi)
    keep writing files inside session directories whose own mtime does not
    change after creation. Filtering only by directory mtime makes live sessions
    disappear after a service restart. This bounded scan keeps the CPU guard but
    keys recency off the actual source file.
    """
    checked = 0
    stack = [Path(directory)]
    while stack and checked < max_files:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if checked >= max_files:
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                            continue
                        checked += 1
                        if core._src_mtime(Path(entry.path)) >= cutoff_mtime:
                            return True
                    except OSError:
                        continue
        except OSError:
            continue
    return False

def ingest_platform(plat: str, states: dict, max_age: float = LIVE_MAX_AGE_S) -> int:
    """Re-parseia as fontes da plataforma (parser dedicado) e ingere. Só parseia
    arquivos modificados nos últimos `max_age` s (pula fontes ociosas).

    O event-loop aplica um teto de re-parse por plataforma (MIN_INTERVAL): o 1º
    evento de uma plataforma ociosa roda imediato (realtime), e rajadas (WAL de
    SQLite em escrita pesada) são coalescidas para ≤1 reparse/MIN_INTERVAL — limita
    CPU sem dropar eventos. O re-parse é idempotente (content-hash)."""
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
                    n = core.ingest(plat, sess, st)
                    if n:
                        core.save_state(plat, st)
                        sent += n
            except Exception as exc:
                print(f"  ⚠ {plat}: {exc}", flush=True)
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

    def refresh() -> set[str]:
        added_platforms: set[str] = set()
        now = time.time()
        for plat, adp in ADAPTERS.items():
            for pattern in adp.get("watch", []):
                is_glob = "*" in pattern   # sentinelas (sem *) nunca são filtradas por mtime
                for d in glob.glob(pattern):
                    if d in watched or not os.path.isdir(d):
                        continue
                    # Dirs expandidos por glob só recebem watch se estiverem na janela ativa;
                    # sentinelas (padrão sem wildcard) são sempre assistidas para detectar sessões novas.
                    if is_glob:
                        try:
                            cutoff = now - WINDOW_S
                            if os.path.getmtime(d) < cutoff and not _dir_has_recent_source(d, cutoff):
                                continue
                        except OSError:
                            continue
                    wd = _libc.inotify_add_watch(fd, d.encode(), MASK)
                    if wd >= 0:
                        wd_plat[wd] = plat
                        watched.add(d)
                        added_platforms.add(plat)
                        print(f"  👁 {plat} [{adp['mode']}]: {d}", flush=True)
                    else:
                        import ctypes
                        err = ctypes.get_errno()
                        print(f"  ⚠ {plat} inotify_add_watch FALHOU para {d}: wd={wd} errno={err}", flush=True)
        return added_platforms

    refresh()
    for plat in ADAPTERS:                 # catch-up histórico no startup
        n = ingest_platform(plat, states, max_age=WINDOW_S)
        if n:
            print(f"  🔄 {plat} catch-up: {n} turn(s)", flush=True)
    last_refresh = time.time()
    print("capture-realtime ativo (inotify, modelo unificado por content-hash).", flush=True)

    # BOUNDEDNESS (incidente 2026-06-17): teto de re-parse por plataforma. O 1º
    # evento de uma plataforma ociosa roda IMEDIATO (realtime preservado); escrita
    # pesada de SQLite (kilo/mimo) é coalescida para ≤1 reparse/MIN_INTERVAL,
    # limitando a CPU sem dropar eventos (pendências são flushadas após o cooldown).
    MIN_INTERVAL = 0.4
    last_ingest: dict[str, float] = {}
    pending: dict[str, float] = {}

    def _do_ingest(plat: str) -> None:
        n = ingest_platform(plat, states)
        last_ingest[plat] = time.time()
        if n:
            print(f"  ⚡ {plat} → {n} turn(s) novo(s)", flush=True)

    while True:
        timeout = max(0.05, MIN_INTERVAL) if pending else 5.0
        r, _, _ = select.select([fd], [], [], timeout)
        now = time.time()
        if r:
            try:
                buf = os.read(fd, 65536)
            except BlockingIOError:
                buf = b""
            i = 0
            touched: set[str] = set()
            ignored_wds: set[int] = set()
            while i + _HDR <= len(buf):
                wd, mask, cookie, nlen = struct.unpack_from("iIII", buf, i)
                i += _HDR + nlen
                plat = wd_plat.get(wd)
                if plat:
                    touched.add(plat)
                if mask & 0x8000:  # IN_IGNORED: watch removido pelo kernel
                    ignored_wds.add(wd)
            for wd in ignored_wds:
                plat = wd_plat.pop(wd, None)
                # remove o caminho correspondente de watched para que refresh() readicione
                if plat:
                    for pattern in ADAPTERS[plat].get("watch", []):
                        for d in glob.glob(pattern):
                            if d in watched:
                                watched.remove(d)
                                print(f"  ♻ {plat} watch removido, será reavistado: {d}", flush=True)
            for plat in touched:
                if now - last_ingest.get(plat, 0.0) >= MIN_INTERVAL:
                    _do_ingest(plat)          # 1º evento: imediato (realtime)
                else:
                    pending[plat] = now       # rajada: coalesce → flush no cooldown
        # flush das pendências cujo cooldown já passou
        for plat in list(pending):
            if time.time() - last_ingest.get(plat, 0.0) >= MIN_INTERVAL:
                _do_ingest(plat)
                pending.pop(plat, None)
        if time.time() - last_refresh > 15:
            for plat in refresh():
                _do_ingest(plat)
            last_refresh = time.time()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
