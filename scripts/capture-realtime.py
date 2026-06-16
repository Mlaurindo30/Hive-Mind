#!/usr/bin/env python3
"""
capture-realtime.py — Daemon de captura em TEMPO REAL via inotify (zero deps).

Replica o fluxo NATIVO do claude-mem (que faz Claude Code/Gemini aparecerem na
hora): cada prompt → POST /api/sessions/init (→ broadcastNewPrompt → SSE), cada
mensagem do agent → POST /api/sessions/observations (discovery: fatos/narrativa),
e summarize no fim do lote. Cada ferramenta com seu platformSource/badge.

Usa inotify (mesmo mecanismo do kernel) → latência de ms. Lê só o que foi
ESCRITO desde a última vez (offset por arquivo); para arquivos já existentes
começa do FIM (histórico é trabalho do timer capture-tailer, com cap).

Multi-plataforma via EXTRACTORS (um extrator por formato de transcript):
  copilot       (workspaceStorage/.../GitHub.copilot-chat/transcripts/*.jsonl)
  antigravity   (~/.gemini/antigravity-cli/brain/*/.system_generated/logs/transcript_full.jsonl)
  hermes        (~/.hermes/sessions/*.jsonl)
  kimi          (~/.kimi/sessions/*/*/context.jsonl)

Reusa _post/_text/load_state/save_state do capture-tailer.py (helpers únicos).
"""
from __future__ import annotations

import ctypes
import glob
import importlib.util
import json
import os
import re
import select
import struct
import sys
import time
import uuid as _uuid
from pathlib import Path

HOME = Path.home()
HERE = Path(__file__).resolve().parent
PROJECT = os.environ.get("CAPTURE_BRIDGE_PROJECT", "Hive-Mind")

_spec = importlib.util.spec_from_file_location("capture_tailer", HERE / "capture-tailer.py")
ct = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ct)

# diretório(s) a vigiar por plataforma (glob → dirs; recarregado a cada 15s)
WATCH_GLOBS = {
    "copilot": [str(HOME / ".config/Code/User/workspaceStorage/*/GitHub.copilot-chat/transcripts")],
    "antigravity": [str(HOME / ".gemini/antigravity-cli/brain/*/.system_generated/logs")],
    "hermes": [str(HOME / ".hermes/sessions")],
    "kimi": [str(HOME / ".kimi/sessions/*/*")],
}

# filtro de nome de arquivo por plataforma (evita transcript duplicado)
FILE_OK = {
    "antigravity": lambda n: n == "transcript_full.jsonl",
    "kimi": lambda n: n == "context.jsonl",
}  # default: qualquer *.jsonl

# Plataformas que NÃO são append-only (array JSON reescrito inteiro, ou SQLite):
# não dá pra "tailar" por offset (não há "linha nova"; o arquivo todo muda). Em vez
# disso, ao detectar QUALQUER mudança no dir vigiado (inotify, ms), RE-PARSEIA a
# fonte com o parser do tailer e ingere só os turns novos (state deduplica) →
# captura ~instantânea, igual ao tail do copilot, com mecanismo diferente.
#   watch   = dirs p/ inotify (o '*' final pega os subdirs de task já existentes)
#   sources = glob dos arquivos a re-parsear quando algo muda
REPARSE = {
    "kilo": {
        "watch": [str(HOME / "snap/code/*/.local/share/kilo")],
        "sources": [str(HOME / "snap/code/*/.local/share/kilo/kilo.db")],
    },
    "roo": {
        "watch": [
            str(HOME / ".config/Code/User/globalStorage/rooveterinaryinc.roo-cline/tasks"),
            str(HOME / ".config/Code/User/globalStorage/rooveterinaryinc.roo-cline/tasks/*"),
        ],
        "sources": [
            str(HOME / ".config/Code/User/globalStorage/rooveterinaryinc.roo-cline/tasks/*/ui_messages.json"),
        ],
    },
}
# Só ingere sessões ativas nas últimas N horas no reparse (evita despejar o
# histórico inteiro de um .db SQLite multi-sessão no 1º evento).
REPARSE_WINDOW_S = 2 * 3600
_last_reparse: dict[str, float] = {}  # debounce por plataforma


# --- EXTRACTORS: linha JSON → ("prompt"|"response"|None, texto) -------------
def _ex_copilot(d):
    t = d.get("type"); data = d.get("data") or {}
    if t == "user.message":
        return "prompt", ct._text(data.get("content"))
    if t == "assistant.message":
        return "response", (ct._text(data.get("content")) or ct._text(data.get("reasoningText")))
    return None, None


def _ex_antigravity(d):
    t = d.get("type")
    if t == "USER_INPUT":
        raw = d.get("content") or ""
        m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.S)
        return "prompt", (m.group(1) if m else raw).strip().strip('"')
    if t == "user":                                  # gemini-cli tmp transcript
        raw = ct._text(d.get("content") or "")
        return "prompt", re.sub(r"<hook_context>.*?</hook_context>", "", raw, flags=re.S).strip()
    if t in ("gemini", "assistant", "model"):
        return "response", ct._text(d.get("content") or "")
    return None, None


def _ex_chat(d):                                      # hermes, kimi (role-based)
    r = d.get("role")
    if r == "user":
        return "prompt", ct._text(d.get("content"))
    if r == "assistant":
        return "response", ct._text(d.get("content"))
    return None, None


EXTRACTORS = {
    "copilot": _ex_copilot,
    "antigravity": _ex_antigravity,
    "hermes": _ex_chat,
    "kimi": _ex_chat,
}


def _sid_for(path: Path, platform: str) -> str:
    m = next((p for p in path.parts if re.fullmatch(r"[0-9a-f-]{36}", p)), None)
    if m:
        return m
    if platform == "copilot":
        return path.stem
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, str(path)))


_libc = ctypes.CDLL("libc.so.6", use_errno=True)
IN_MODIFY = 0x2; IN_CLOSE_WRITE = 0x8; IN_MOVED_TO = 0x80; IN_CREATE = 0x100
MASK = IN_MODIFY | IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE
_HDR = struct.calcsize("iIII")


def process_realtime(platform: str, path: Path, state: dict) -> int:
    """Lê o que foi escrito desde o último offset e emite init/observation."""
    extract = EXTRACTORS[platform]
    key = f"rt:{platform}:{path}"
    rec = state.setdefault(key, {"offset": 0, "sid": None})
    try:
        size = path.stat().st_size
    except OSError:
        return 0
    if rec["offset"] > size:
        rec["offset"] = 0
        rec["sid"] = None
    try:
        with open(path, "rb") as f:
            f.seek(rec["offset"])
            chunk = f.read()
            rec["offset"] = f.tell()
    except OSError:
        return 0

    sid = rec.get("sid") or _sid_for(path, platform)
    sent = 0
    last_assistant = None
    for raw in chunk.split(b"\n"):
        raw = raw.strip()
        if not raw.startswith(b"{"):
            continue
        try:
            d = json.loads(raw)
        except Exception:
            continue
        # session.start (copilot) atualiza o sid
        if d.get("type") == "session.start":
            sid = (d.get("data") or {}).get("sessionId") or sid
            continue
        kind, txt = extract(d)
        if not txt:
            continue
        if kind == "prompt":
            ct._post("/api/sessions/init", {
                "contentSessionId": sid, "project": PROJECT, "platformSource": platform,
                "prompt": txt, "customTitle": f"[{platform}] {txt[:60]}",
            })
            sent += 1
        elif kind == "response":
            mid = d.get("id") or (d.get("data") or {}).get("messageId") or f"m{rec['offset']}"
            ct._post("/api/sessions/observations", {
                "contentSessionId": sid, "tool_name": f"{platform.capitalize()}Message",
                "tool_input": {}, "tool_response": {"result": txt[:6000]},
                "platformSource": platform, "cwd": str(Path.cwd()),
                "tool_use_id": f"{platform}:{sid}:{mid}",
            })
            last_assistant = txt
            sent += 1
    rec["sid"] = sid
    if last_assistant:
        ct._post("/api/sessions/summarize", {
            "contentSessionId": sid, "platformSource": platform,
            "last_assistant_message": last_assistant[:4000],
            "lastAssistantMessage": last_assistant[:4000],
        })
    return sent


def reparse_ingest(platform: str, state: dict) -> int:
    """Re-parseia as fontes da plataforma (via parser do tailer) e ingere só os
    turns novos. Debounced; limita a sessões ativas em REPARSE_WINDOW_S p/ DBs."""
    now = time.time()
    if now - _last_reparse.get(platform, 0) < 1.5:   # debounce (WAL gera N eventos)
        return 0
    _last_reparse[platform] = now
    ct.SESSION_CUTOFF_MS = int((now - REPARSE_WINDOW_S) * 1000)
    parser = ct.PARSERS[platform]
    sent = 0
    for pattern in REPARSE[platform]["sources"]:
        for src in glob.glob(pattern):
            p = Path(src)
            if not p.is_file():
                continue
            try:
                for sess in parser(p):
                    sent += ct.ingest(platform, sess, state)
            except Exception as exc:
                print(f"  ⚠ reparse {platform}: {exc}", flush=True)
    return sent


def main() -> int:
    while not ct.worker_alive():
        print(f"aguardando worker em {ct.BASE}...", flush=True)
        time.sleep(3)
    fd = _libc.inotify_init1(os.O_NONBLOCK)
    if fd < 0:
        print("inotify_init1 falhou", file=sys.stderr)
        return 1
    wd_dir: dict[int, tuple[str, str]] = {}
    watched: set[str] = set()
    state = ct.load_state()

    def file_ok(platform: str, name: str) -> bool:
        if not name.endswith(".jsonl"):
            return False
        f = FILE_OK.get(platform)
        return f(name) if f else True

    def refresh():
        for platform, patterns in WATCH_GLOBS.items():
            for pattern in patterns:
                for d in glob.glob(pattern):
                    if d in watched or not os.path.isdir(d):
                        continue
                    wd = _libc.inotify_add_watch(fd, d.encode(), MASK)
                    if wd >= 0:
                        wd_dir[wd] = (platform, d)
                        watched.add(d)
                        # anti-flood: pré-semeia offset=tamanho dos arquivos já
                        # existentes (só processa o que for escrito daqui pra frente)
                        for fp in glob.glob(os.path.join(d, "*.jsonl")):
                            if file_ok(platform, os.path.basename(fp)):
                                k = f"rt:{platform}:{fp}"
                                if k not in state:
                                    try:
                                        state[k] = {"offset": os.path.getsize(fp), "sid": None}
                                    except OSError:
                                        pass
                        print(f"  👁 {platform}: {d}", flush=True)
        # plataformas de reparse: vigia os dirs; qualquer evento dispara re-parse
        for platform, cfg in REPARSE.items():
            for pattern in cfg["watch"]:
                for d in glob.glob(pattern):
                    if d in watched or not os.path.isdir(d):
                        continue
                    wd = _libc.inotify_add_watch(fd, d.encode(), MASK)
                    if wd >= 0:
                        wd_dir[wd] = (platform, d)
                        watched.add(d)
                        print(f"  👁 {platform} (reparse): {d}", flush=True)

    refresh()
    # Catch-up histórico: re-parseia plataformas REPARSE uma vez no startup para
    # capturar sessões anteriores ao início do daemon (substitui o tailer p/ kilo/roo).
    for _plat in REPARSE:
        _n = reparse_ingest(_plat, state)
        if _n:
            dirty = True
            print(f"  🔄 {_plat} catch-up: {_n} turn(s)", flush=True)
    last_refresh = last_save = time.time()
    dirty = dirty  # mantém flag se catch-up gerou dados
    print("capture-realtime ativo (inotify, multi-plataforma).", flush=True)

    while True:
        r, _, _ = select.select([fd], [], [], 5.0)
        now = time.time()
        if r:
            try:
                buf = os.read(fd, 65536)
            except BlockingIOError:
                buf = b""
            i = 0
            touched: set[tuple[str, str]] = set()
            touched_reparse: set[str] = set()
            while i + _HDR <= len(buf):
                wd, mask, cookie, nlen = struct.unpack_from("iIII", buf, i)
                i += _HDR
                name = buf[i:i + nlen].split(b"\x00", 1)[0].decode("utf-8", "ignore")
                i += nlen
                info = wd_dir.get(wd)
                if not info:
                    continue
                platform = info[0]
                if platform in REPARSE:               # qualquer mudança → re-parse
                    touched_reparse.add(platform)
                elif file_ok(platform, name):          # append-only → tail por offset
                    touched.add((platform, os.path.join(info[1], name)))
            for platform, fp in touched:
                p = Path(fp)
                if p.is_file():
                    n = process_realtime(platform, p, state)
                    if n:
                        dirty = True
                        print(f"  ⚡ {platform}:{p.stem[:12]} → {n} evento(s)", flush=True)
            for platform in touched_reparse:
                n = reparse_ingest(platform, state)
                if n:
                    # Salva imediatamente após reparse para que o tailer (30s) veja
                    # os turns já marcados como done → elimina corrida de estado.
                    ct.save_state(state)
                    last_save = now
                    dirty = False
                    print(f"  ⚡ {platform} (reparse) → {n} turn(s) novo(s)", flush=True)
        if now - last_refresh > 15:
            refresh(); last_refresh = now
        if dirty and now - last_save > 2:
            ct.save_state(state); dirty = False; last_save = now


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
