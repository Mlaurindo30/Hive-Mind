#!/usr/bin/env python3
"""
capture_core.py — Infraestrutura ÚNICA de transporte do pipeline de captura.

Contém SÓ o que é genérico e não pertence a nenhuma ferramenta específica:
  • conexão com o worker do claude-mem (_post / worker_alive)
  • idempotência por CONTENT-HASH (content_hash / _norm)
  • motor de ingestão (ingest) — emite init/observation/summarize sem duplicar
  • SeenStore — estado persistido em SQLite com WAL (substitui JSON por plataforma)
  • utilitários de mtime (WAL-aware) e coerção de texto

NÃO contém lógica de parsing de NENHUMA ferramenta — cada uma tem seu próprio
módulo em parsers/<tool>.py. Aqui é a única camada compartilhada (transporte).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parent.parent.parent
BASE = f"http://{os.environ.get('CLAUDE_MEM_WORKER_HOST','127.0.0.1')}:{os.environ.get('CLAUDE_MEM_WORKER_PORT','37700')}"
DATA_DIR = Path(os.environ.get("CLAUDE_MEM_DATA_DIR", str(ROOT / "claude-mem" / "data")))
PROJECT = os.environ.get("CAPTURE_BRIDGE_PROJECT", "Hive-Mind")
OBS_CAP = int(os.environ.get("CAPTURE_TAILER_OBS_CAP", "0"))
SESSION_CUTOFF_MS = 0

# Mantidos para referência na migração one-shot (não usar para estado novo).
STATE = DATA_DIR / "tailer-state.json"
STATE_DIR = DATA_DIR / "capture-state"


# ── util de texto ──────────────────────────────────────────────────────────────
def text_content(c) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        t = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("text"))
        return t or json.dumps(c, ensure_ascii=False)[:2000]
    return str(c or "")


_text = text_content  # alias legado


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def content_hash(*parts: str) -> str:
    """Identidade ESTÁVEL de um prompt/observação: independe de offset, índice ou
    ordem de reescrita do arquivo. Mesma mensagem → mesmo hash → emitida 1× só,
    não importa quantas vezes a fonte seja re-parseada ou por quantos processos.
    Vira também o tool_use_id, então o worker deduplica entre processos."""
    return hashlib.sha1("|".join(parts).encode("utf-8", errors="ignore")).hexdigest()


def project_from_cwd(directory: str | None) -> str | None:
    if not directory:
        return None
    name = os.path.basename(str(directory).rstrip("/"))
    return name or None


# ── mtime WAL-aware ────────────────────────────────────────────────────────────
def _src_mtime(p: Path) -> float:
    mt = 0.0
    for cand in (p, Path(str(p) + "-wal"), Path(str(p) + "-shm")):
        try:
            mt = max(mt, cand.stat().st_mtime)
        except OSError:
            pass
    return mt


# ── conexão com o worker ───────────────────────────────────────────────────────
def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode() or "{}")
    except Exception as e:
        msg = ""
        if hasattr(e, "read"):
            try:
                msg = e.read().decode()[:200]
            except Exception:
                pass
        print(f"  ⚠ {path}: {e} {msg}")
        return {"error": str(e)}


def worker_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE}/api/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


# ── SeenStore: estado persistido em SQLite ─────────────────────────────────────
class SeenStore:
    """Armazena hashes de conteúdo já emitidos em SQLite com WAL.

    Substitui os arquivos capture-state/<platform>.json. Cada add() comita
    imediatamente — se o processo cair entre um emit e o próximo, no máximo
    um hash é re-emitido. Dois processos simultâneos nunca duplicam graças ao
    INSERT OR IGNORE com PRIMARY KEY (platform, sid, hash).
    """

    _DB_NAME = "capture-state.db"
    _SENTINEL = "capture-state/.migrated-to-sqlite"

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or (DATA_DIR / self._DB_NAME)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self._path), timeout=30, check_same_thread=False)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=NORMAL")
        self._con.execute("PRAGMA busy_timeout=10000")
        self._con.executescript("""
            CREATE TABLE IF NOT EXISTS session_meta (
                platform TEXT NOT NULL,
                sid      TEXT NOT NULL,
                inited   INTEGER NOT NULL DEFAULT 0,
                ts       INTEGER NOT NULL,
                PRIMARY KEY (platform, sid)
            );
            CREATE TABLE IF NOT EXISTS seen_hashes (
                platform TEXT NOT NULL,
                sid      TEXT NOT NULL,
                hash     TEXT NOT NULL,
                ts       INTEGER NOT NULL,
                PRIMARY KEY (platform, sid, hash)
            );
            CREATE INDEX IF NOT EXISTS seen_hashes_ts ON seen_hashes(ts);
        """)
        self._con.commit()
        self._migrate_from_json()

    def _migrate_from_json(self) -> None:
        # Sentinel lives next to the DB, not in DATA_DIR — prevents test runs
        # (which pass a custom db_path) from writing the sentinel into the
        # production data directory and accidentally skipping the real migration.
        sentinel = self._path.parent / ".migrated-to-sqlite"
        if sentinel.exists():
            return
        # Custom db_path means test / one-shot usage: start empty, no migration.
        if self._path != (DATA_DIR / self._DB_NAME):
            sentinel.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
            return
        json_files = list(STATE_DIR.glob("*.json")) if STATE_DIR.exists() else []
        if not json_files:
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
            return
        now = int(time.time())
        migrated = 0
        for f in json_files:
            if f.suffix == ".tmp":
                continue
            platform = f.stem
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            for skey, rec in data.items():
                if not isinstance(rec, dict):
                    continue
                # skey pode ser "platform:sid" ou "rt:platform:sid" (formato legado)
                parts = skey.split(":")
                sid = parts[-1] if len(parts) >= 2 else skey
                ts = int(rec.get("ts") or now)
                inited = 1 if rec.get("inited") else 0
                self._con.execute(
                    "INSERT OR IGNORE INTO session_meta(platform,sid,inited,ts) VALUES(?,?,?,?)",
                    (platform, sid, inited, ts),
                )
                for h in (rec.get("seen") or []):
                    self._con.execute(
                        "INSERT OR IGNORE INTO seen_hashes(platform,sid,hash,ts) VALUES(?,?,?,?)",
                        (platform, sid, h, ts),
                    )
                    migrated += 1
        self._con.commit()
        sentinel.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
        if migrated:
            print(f"  ✓ migração JSON→SQLite: {migrated} hashes importados")

    def contains(self, platform: str, sid: str, h: str) -> bool:
        return self._con.execute(
            "SELECT 1 FROM seen_hashes WHERE platform=? AND sid=? AND hash=? LIMIT 1",
            (platform, sid, h),
        ).fetchone() is not None

    def add(self, platform: str, sid: str, h: str) -> None:
        self._con.execute(
            "INSERT OR IGNORE INTO seen_hashes(platform,sid,hash,ts) VALUES(?,?,?,?)",
            (platform, sid, h, int(time.time())),
        )
        self._con.commit()

    def is_inited(self, platform: str, sid: str) -> bool:
        row = self._con.execute(
            "SELECT inited FROM session_meta WHERE platform=? AND sid=? LIMIT 1",
            (platform, sid),
        ).fetchone()
        return bool(row and row[0])

    def mark_inited(self, platform: str, sid: str) -> None:
        self._con.execute(
            "INSERT INTO session_meta(platform,sid,inited,ts) VALUES(?,?,1,?) "
            "ON CONFLICT(platform,sid) DO UPDATE SET inited=1, ts=excluded.ts",
            (platform, sid, int(time.time())),
        )
        self._con.commit()

    def touch(self, platform: str, sid: str) -> None:
        self._con.execute(
            "INSERT INTO session_meta(platform,sid,inited,ts) VALUES(?,?,0,?) "
            "ON CONFLICT(platform,sid) DO UPDATE SET ts=excluded.ts",
            (platform, sid, int(time.time())),
        )
        self._con.commit()

    def prune(self, cutoff_ts: int) -> int:
        c1 = self._con.execute(
            "DELETE FROM seen_hashes WHERE ts < ?", (cutoff_ts,)
        ).rowcount
        c2 = self._con.execute(
            "DELETE FROM session_meta WHERE ts < ?", (cutoff_ts,)
        ).rowcount
        self._con.commit()
        return c1 + c2

    def close(self) -> None:
        self._con.close()


# ── motor de ingestão (idempotente por content-hash) ───────────────────────────
def ingest(platform: str, sess: dict, store: SeenStore) -> int:
    """Emite prompt/observação/sumário ao worker, deduplicando por content-hash.
    `sess` = {sid, prompt, turns:[{tool_name, tool_input:{prompt?}, tool_response}], last}.
    `store` = SeenStore compartilhado. Re-chamar com a mesma sessão N vezes
    (reparse / reescrita / 2 processos) → só conteúdo NOVO emite."""
    from core.telemetry import init_telemetry, span
    init_telemetry()
    sid = sess.get("sid")
    prompt = sess.get("prompt")
    prompts = sess.get("prompts") or []
    turns, last_text = sess.get("turns") or [], sess.get("last")
    if not sid or (not prompt and not turns):
        return 0

    store.touch(platform, sid)

    with span("capture.ingest", {"platform": platform, "sid": sid, "turns_count": len(turns)}):
        return _ingest_body(platform, sess, store, sid, prompt, prompts, turns, last_text)


def _ingest_body(platform, sess, store, sid, prompt, prompts, turns, last_text) -> int:
    """Corpo de ingest() extraído p/ permitir wrap por span de telemetria P9."""
    proj = sess.get("project") or PROJECT
    cwd = sess.get("cwd") or str(Path.cwd())

    def emit_prompt(text: str) -> bool:
        norm = _norm(text)
        if not norm:
            return False
        h = content_hash(sid, "p", norm)
        if store.contains(platform, sid, h):
            return False
        _post("/api/sessions/init", {
            "contentSessionId": sid, "project": proj, "platformSource": platform,
            "prompt": text, "customTitle": f"[{platform}] {text[:60]}",
        })
        store.add(platform, sid, h)
        return True

    if not store.is_inited(platform, sid):
        _post("/api/sessions/init", {
            "contentSessionId": sid, "project": proj, "platformSource": platform,
            "prompt": prompt or "(sessão)", "customTitle": f"[{platform}] {(prompt or '')[:60]}",
        })
        store.mark_inited(platform, sid)
        if prompt:
            store.add(platform, sid, content_hash(sid, "p", _norm(prompt)))

    for item in prompts:
        emit_prompt(str(item))

    sent = 0
    for t in turns:
        if OBS_CAP and sent >= OBS_CAP:
            print(f"  ⏳ {platform}:{sid[:12]}: cap {OBS_CAP} atingido; resto depois")
            break
        if isinstance(t.get("tool_input"), dict):
            tp = str(t["tool_input"].get("prompt") or "").strip()
            if tp:
                emit_prompt(tp)
        tn = (t.get("tool_name") or "Tool").strip() or "Tool"
        resp = str(t.get("tool_response") or "")
        ho = content_hash(sid, "o", tn, _norm(resp))
        if store.contains(platform, sid, ho):
            continue
        obs_res = _post("/api/sessions/observations", {
            "contentSessionId": sid, "tool_name": tn,
            "tool_input": t.get("tool_input") or {}, "tool_response": {"result": resp},
            "platformSource": platform, "cwd": cwd,
            "tool_use_id": f"{platform}:{sid}:{ho[:20]}",
        })
        if obs_res.get("error") or obs_res.get("stored") is False:
            continue
        store.add(platform, sid, ho)
        sent += 1

    if sent:
        _post("/api/sessions/summarize", {
            "contentSessionId": sid, "platformSource": platform,
            "last_assistant_message": last_text or prompt or "sessão concluída",
        })
        print(f"  ✓ {platform}:{sid[:12]} → {sent} nova(s)")
    return sent


# ── stubs de compatibilidade (não usar em código novo) ─────────────────────────
def _migrate_legacy_state() -> None:
    """Migração legada JSON→JSON por plataforma. Mantido para compatibilidade."""
    if not STATE.exists() or (STATE_DIR / ".migrated").exists():
        return
    try:
        legacy = json.loads(STATE.read_text())
    except Exception:
        return
    buckets: dict[str, dict] = {}
    for skey, val in legacy.items():
        plat = skey.split(":", 2)[1] if skey.startswith("rt:") else (
            skey.split(":", 1)[0] if ":" in skey else skey)
        buckets.setdefault(plat, {})[skey] = val
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for plat, data in buckets.items():
        save_state(plat, data)
    (STATE_DIR / ".migrated").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))


def load_state(platform: str) -> dict:
    """Legado. Novo código deve usar SeenStore()."""
    _migrate_legacy_state()
    p = STATE_DIR / f"{platform}.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def save_state(platform: str, s: dict) -> None:
    """Legado. Novo código deve usar SeenStore()."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = STATE_DIR / f"{platform}.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, indent=2))
    tmp.replace(p)
