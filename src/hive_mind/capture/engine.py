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
import threading
import sys
import time
import urllib.request
from pathlib import Path

# Bootstrap: adiciona project root ao sys.path para que `from core.X import ...`
# funcione quando o script é executado via `python /path/script.py` (systemd).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

HOME = Path.home()
# src/hive_mind/capture/engine.py -> project root is four levels up. Derived
# via the resolver when possible, so the constant does not silently depend on
# where in the tree this file lives.
def _project_root() -> Path:
    try:
        from hive_mind.project import resolve_project_root
        return resolve_project_root()
    except Exception:
        return Path(__file__).resolve().parents[3]


ROOT = _project_root()


class CanonicalIdentityRequired(RuntimeError):
    """The transport was handed a session nobody resolved an identity for."""
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

def _safe_print(message: str, *, stream=None) -> None:
    """Write diagnostics without crashing on legacy Windows console encodings."""
    target = stream or sys.stdout
    try:
        print(message, file=target, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(target, "encoding", None) or "ascii"
        safe = message.encode(encoding, errors="backslashreplace").decode(encoding)
        print(safe, file=target, flush=True)

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
        _safe_print(f"  ⚠ {path}: {e} {msg}")
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

    def __init__(
        self,
        db_path: Path | None = None,
        legacy_db_path: Path | None = None,
    ) -> None:
        self._path = db_path or (DATA_DIR / self._DB_NAME)
        self._legacy_db_path = (
            legacy_db_path
            if legacy_db_path is not None
            else HOME / ".claude-mem" / self._DB_NAME
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(self._path), timeout=30, check_same_thread=False)
        self._lock = threading.RLock()
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
        self._migrate_from_legacy_sqlite()
        self._migrate_from_json()

    def _migrate_from_legacy_sqlite(self) -> None:
        legacy = self._legacy_db_path
        if not legacy.is_file() or legacy.resolve() == self._path.resolve():
            return
        try:
            with sqlite3.connect(f"file:{legacy.as_posix()}?mode=ro", uri=True) as source:
                tables = {
                    row[0]
                    for row in source.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            if not {"session_meta", "seen_hashes"}.issubset(tables):
                return
            self._con.execute("ATTACH DATABASE ? AS legacy_state", (str(legacy),))
            try:
                self._con.execute(
                    """
                    INSERT OR IGNORE INTO seen_hashes(platform, sid, hash, ts)
                    SELECT platform, sid, hash, ts FROM legacy_state.seen_hashes
                    """
                )
                self._con.execute(
                    """
                    INSERT OR IGNORE INTO session_meta(platform, sid, inited, ts)
                    SELECT platform, sid, inited, ts FROM legacy_state.session_meta
                    """
                )
                self._con.execute(
                    """
                    UPDATE session_meta
                    SET inited = MAX(
                            inited,
                            COALESCE((
                                SELECT legacy.inited
                                FROM legacy_state.session_meta AS legacy
                                WHERE legacy.platform = session_meta.platform
                                  AND legacy.sid = session_meta.sid
                            ), inited)
                        ),
                        ts = MAX(
                            ts,
                            COALESCE((
                                SELECT legacy.ts
                                FROM legacy_state.session_meta AS legacy
                                WHERE legacy.platform = session_meta.platform
                                  AND legacy.sid = session_meta.sid
                            ), ts)
                        )
                    WHERE EXISTS (
                        SELECT 1
                        FROM legacy_state.session_meta AS legacy
                        WHERE legacy.platform = session_meta.platform
                          AND legacy.sid = session_meta.sid
                    )
                    """
                )
                self._con.commit()
            finally:
                self._con.execute("DETACH DATABASE legacy_state")
        except (OSError, sqlite3.Error) as exc:
            _safe_print(f"  ⚠ migração do checkpoint legado ignorada: {exc}")

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
            _safe_print(f"  ✓ migração JSON→SQLite: {migrated} hashes importados")

    def contains(self, platform: str, sid: str, h: str) -> bool:
        with self._lock:
            return self._con.execute(
                "SELECT 1 FROM seen_hashes WHERE platform=? AND sid=? AND hash=? LIMIT 1",
                (platform, sid, h),
            ).fetchone() is not None

    def add(self, platform: str, sid: str, h: str) -> None:
        with self._lock:
            self._con.execute(
                "INSERT OR IGNORE INTO seen_hashes(platform,sid,hash,ts) VALUES(?,?,?,?)",
                (platform, sid, h, int(time.time())),
            )
            self._con.commit()

    def is_inited(self, platform: str, sid: str) -> bool:
        with self._lock:
            row = self._con.execute(
                "SELECT inited FROM session_meta WHERE platform=? AND sid=? LIMIT 1",
                (platform, sid),
            ).fetchone()
            return bool(row and row[0])

    def mark_inited(self, platform: str, sid: str) -> None:
        with self._lock:
            self._con.execute(
                "INSERT INTO session_meta(platform,sid,inited,ts) VALUES(?,?,1,?) "
                "ON CONFLICT(platform,sid) DO UPDATE SET inited=1, ts=excluded.ts",
                (platform, sid, int(time.time())),
            )
            self._con.commit()

    def touch(self, platform: str, sid: str) -> None:
        with self._lock:
            self._con.execute(
                "INSERT INTO session_meta(platform,sid,inited,ts) VALUES(?,?,0,?) "
                "ON CONFLICT(platform,sid) DO UPDATE SET ts=excluded.ts",
                (platform, sid, int(time.time())),
            )
            self._con.commit()

    def prune(self, cutoff_ts: int) -> int:
        with self._lock:
            c1 = self._con.execute(
                "DELETE FROM seen_hashes WHERE ts < ?", (cutoff_ts,)
            ).rowcount
            c2 = self._con.execute(
                "DELETE FROM session_meta WHERE ts < ?", (cutoff_ts,)
            ).rowcount
            self._con.commit()
            return c1 + c2

    def close(self) -> None:
        with self._lock:
            self._con.close()


# ── motor de ingestão (idempotente por content-hash) ───────────────────────────
def emit(platform: str, sess: dict, store: SeenStore) -> int:
    """Transport only: emit prompt/observation/summary, deduped by content-hash.

    Identity is **not** decided here. This function requires a session that
    has already been through ``hive_mind.capture.identity.apply_identity``,
    and refuses one that has not.

    It used to fall back to whatever the parser called the project:

        proj = sess.get("project_name") or sess.get("project") or PROJECT

    which is how prompt text and a worktree name became projects in real
    data. The fallback is gone; the guard below replaces it.
    `sess` = {sid, prompt, turns:[{tool_name, tool_input:{prompt?}, tool_response}], last}.
    `store` = SeenStore compartilhado. Re-chamar com a mesma sessão N vezes
    (reparse / reescrita / 2 processos) → só conteúdo NOVO emite."""
    from core.telemetry import init_telemetry, span
    init_telemetry()
    sid = sess.get("sid")
    prompt = sess.get("prompt")
    prompts = sess.get("prompts") or []
    turns, last_text = sess.get("turns") or [], sess.get("last")
    messages = sess.get("messages") or []
    if not sid or (not prompt and not turns and not messages):
        return 0

    store.touch(platform, sid)

    with span(
        "capture.emit",
        {
            "platform": platform,
            "sid": sid,
            "turns_count": len(turns),
            "messages_count": len(messages),
        },
    ):
        return _emit_body(platform, sess, store, sid, prompt, prompts, turns, last_text)


def _emit_body(platform, sess, store, sid, prompt, prompts, turns, last_text) -> int:
    """Corpo de emit() extraído p/ permitir wrap por span de telemetria P9."""
    envelope = sess.get("project_identity")
    if not isinstance(envelope, dict) or not envelope.get("project_name"):
        raise CanonicalIdentityRequired(
            f"{platform}: session reached the transport without a canonical "
            "identity. Call hive_mind.capture.ingest.ingest(), which resolves "
            "it, instead of the transport directly."
        )
    proj = envelope["project_name"]
    cwd = sess.get("cwd") or str(Path.cwd())
    identity_metadata = {"project_identity": dict(envelope)}
    capture_audit = (sess.get("metadata") or {}).get("capture")
    prompt_events = [
        item for item in (sess.get("prompt_events") or [])
        if isinstance(item, dict) and str(item.get("content") or "").strip()
    ]
    if isinstance(capture_audit, dict):
        identity_metadata["capture"] = dict(capture_audit)

    def with_identity(payload: dict) -> dict:
        metadata = payload.get("metadata")
        merged = dict(metadata) if isinstance(metadata, dict) else {}
        if identity_metadata is not None:
            merged.update(identity_metadata)
        if merged:
            payload["metadata"] = merged
        return payload

    def emit_prompt(
        text: str,
        *,
        timestamp=None,
        metadata: dict | None = None,
        event_key: str | None = None,
    ) -> bool:
        norm = _norm(text)
        if not norm:
            return False
        h = content_hash(sid, "p-event", event_key) if event_key else content_hash(sid, "p", norm)
        if store.contains(platform, sid, h):
            return False
        payload = {
            "contentSessionId": sid,
            "project": proj,
            "platformSource": platform,
            "prompt": text,
            "customTitle": f"[{platform}] {text[:60]}",
        }
        if timestamp is not None:
            payload["timestamp"] = timestamp
        if metadata:
            payload["metadata"] = metadata
        init_res = _post("/api/sessions/init", with_identity(payload))
        if init_res.get("error") or init_res.get("stored") is False:
            return False
        store.add(platform, sid, h)
        return True

    messages = sess.get("messages") or []
    if messages:
        sent = 0
        last_user = None
        last_assistant = None
        last_assistant_timestamp = None

        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip().lower()
            content = str(message.get("content") or "").strip()
            timestamp = message.get("timestamp")
            if not role or not content:
                continue

            message_type = "prompt" if role == "user" else role
            event_metadata = {
                "message_role": role,
                "message_type": message_type,
            }
            if timestamp is not None:
                event_metadata["timestamp"] = timestamp

            if role == "user":
                if not store.is_inited(platform, sid):
                    norm = _norm(content)
                    h = content_hash(sid, "p", norm)
                    payload = {
                        "contentSessionId": sid,
                        "project": proj,
                        "platformSource": platform,
                        "prompt": content,
                        "customTitle": f"[{platform}] {content[:60]}",
                        "metadata": event_metadata,
                    }
                    if timestamp is not None:
                        payload["timestamp"] = timestamp
                    init_res = _post("/api/sessions/init", with_identity(payload))
                    if not init_res.get("error") and init_res.get("stored") is not False:
                        store.mark_inited(platform, sid)
                        store.add(platform, sid, h)
                else:
                    emit_prompt(
                        content,
                        timestamp=timestamp,
                        metadata=event_metadata,
                    )
                last_user = content
                continue

            if role not in {"assistant", "tool"}:
                continue
            if OBS_CAP and sent >= OBS_CAP:
                _safe_print(f"  ⏳ {platform}:{sid[:12]}: cap {OBS_CAP} atingido; resto depois")
                break

            tool_name = "Message" if role == "assistant" else str(
                message.get("tool_name") or message.get("name") or "Tool"
            ).strip() or "Tool"
            tool_input = (
                dict(message["tool_input"])
                if isinstance(message.get("tool_input"), dict)
                else {}
            )
            tool_input["message_role"] = role
            tool_input["message_type"] = message_type
            if timestamp is not None:
                tool_input["timestamp"] = timestamp
            if role == "assistant" and last_user and not tool_input.get("prompt"):
                tool_input["prompt"] = last_user
            if role == "tool":
                event_metadata["tool_name"] = tool_name

            observation_hash = content_hash(
                sid,
                "o",
                tool_name,
                _norm(content),
            )
            if store.contains(platform, sid, observation_hash):
                if role == "assistant":
                    last_assistant = content
                    last_assistant_timestamp = timestamp
                continue

            payload = {
                "contentSessionId": sid,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_response": {"result": content},
                "platformSource": platform,
                "cwd": cwd,
                "tool_use_id": f"{platform}:{sid}:{observation_hash[:20]}",
                "metadata": event_metadata,
            }
            if timestamp is not None:
                payload["timestamp"] = timestamp
            observation_res = _post(
                "/api/sessions/observations",
                with_identity(payload),
            )
            if observation_res.get("error") or observation_res.get("stored") is False:
                continue
            store.add(platform, sid, observation_hash)
            sent += 1
            if role == "assistant":
                last_assistant = content
                last_assistant_timestamp = timestamp

        if sent:
            summary_metadata = {"message_type": "summary"}
            if last_assistant_timestamp is not None:
                summary_metadata["timestamp"] = last_assistant_timestamp
            summary_payload = {
                "contentSessionId": sid,
                "platformSource": platform,
                "last_assistant_message": (
                    last_assistant or last_text or prompt or "sessão concluída"
                ),
                "metadata": summary_metadata,
            }
            if last_assistant_timestamp is not None:
                summary_payload["timestamp"] = last_assistant_timestamp
            _post(
                "/api/sessions/summarize",
                with_identity(summary_payload),
            )
            _safe_print(f"  [ok] {platform}:{sid[:12]} -> {sent} nova(s)")
        return sent
    if not store.is_inited(platform, sid):
        first_event = prompt_events[0] if prompt_events else None
        first_event_key = None
        first_metadata = None
        if first_event is not None:
            first_event_key = str(
                first_event.get("event_id") or first_event.get("source_position") or ""
            ).strip() or None
            first_metadata = {
                "source_event_id": first_event.get("event_id"),
                "source_position": first_event.get("source_position"),
            }
            first_metadata = {key: value for key, value in first_metadata.items() if value is not None}
        initial_payload = {
            "contentSessionId": sid, "project": proj, "platformSource": platform,
            "prompt": prompt or "(sessão)", "customTitle": f"[{platform}] {(prompt or '')[:60]}",
        }
        if first_metadata:
            initial_payload["metadata"] = first_metadata
        init_res = _post("/api/sessions/init", with_identity(initial_payload))
        if not init_res.get("error") and init_res.get("stored") is not False:
            store.mark_inited(platform, sid)
            if prompt:
                initial_hash = (
                    content_hash(sid, "p-event", first_event_key)
                    if first_event_key else content_hash(sid, "p", _norm(prompt))
                )
                store.add(platform, sid, initial_hash)

    if prompt_events:
        for event in prompt_events:
            event_id = event.get("event_id")
            source_position = event.get("source_position")
            event_key = str(event_id or source_position or "").strip() or None
            metadata = {
                "source_event_id": event_id,
                "source_position": source_position,
            }
            emit_prompt(
                str(event["content"]),
                timestamp=event.get("timestamp"),
                metadata={key: value for key, value in metadata.items() if value is not None},
                event_key=event_key,
            )
    else:
        for item in prompts:
            emit_prompt(str(item))

    sent = 0
    for t in turns:
        if OBS_CAP and sent >= OBS_CAP:
            _safe_print(f"  ⏳ {platform}:{sid[:12]}: cap {OBS_CAP} atingido; resto depois")
            break
        if not prompt_events and isinstance(t.get("tool_input"), dict):
            tp = str(t["tool_input"].get("prompt") or "").strip()
            if tp:
                emit_prompt(tp)
        tn = (t.get("tool_name") or "Tool").strip() or "Tool"
        resp = str(t.get("tool_response") or "")
        ho = content_hash(sid, "o", tn, _norm(resp))
        if store.contains(platform, sid, ho):
            continue
        obs_res = _post("/api/sessions/observations", with_identity({
            "contentSessionId": sid, "tool_name": tn,
            "tool_input": t.get("tool_input") or {}, "tool_response": {"result": resp},
            "platformSource": platform, "cwd": cwd,
            "tool_use_id": f"{platform}:{sid}:{ho[:20]}",
        }))
        if obs_res.get("error") or obs_res.get("stored") is False:
            continue
        store.add(platform, sid, ho)
        sent += 1

    if sent:
        _post("/api/sessions/summarize", with_identity({
            "contentSessionId": sid, "platformSource": platform,
            "last_assistant_message": last_text or prompt or "sessão concluída",
        }))
        _safe_print(f"  [ok] {platform}:{sid[:12]} -> {sent} nova(s)")
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
