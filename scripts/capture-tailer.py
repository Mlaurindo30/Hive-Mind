#!/usr/bin/env python3
"""
capture-tailer.py — Ingestor de transcripts → worker do claude-mem.

Lê o histórico/transcript que cada ferramenta JÁ escreve e replica, via a MESMA
API nativa que claude/gemini usam (`/api/sessions/init|observations|summarize`),
preservando a SEPARAÇÃO por ferramenta (cada uma com seu `platformSource`/badge
no viewer :37700). Não toca nos binários das ferramentas (não-invasivo) e cobre
tanto CLI quanto IDE (ambos escrevem transcript).

Idempotente: guarda o que já enviou em ~/.claude-mem/tailer-state.json.
Projetado para ser disparado por EVENTO (systemd .path), não em loop apertado.

Plataformas:
  antigravity  → ~/.gemini/antigravity-cli/brain/<uuid>/.system_generated/logs/transcript_full.jsonl
    openclaw     → ~/.openclaw/tasks/runs.sqlite

Uso:
  capture-tailer.py --platform antigravity --scan         # ingere o que há de novo
  capture-tailer.py --platform antigravity --source <jsonl>
"""
from __future__ import annotations

import argparse
import difflib
import glob
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
BASE = f"http://{os.environ.get('CLAUDE_MEM_WORKER_HOST','127.0.0.1')}:{os.environ.get('CLAUDE_MEM_WORKER_PORT','37700')}"
DATA_DIR = Path(os.environ.get("CLAUDE_MEM_DATA_DIR", str(HOME / ".claude-mem")))
STATE = DATA_DIR / "tailer-state.json"
PROJECT = os.environ.get("CAPTURE_BRIDGE_PROJECT", "Hive-Mind")
# Máx. de observações por sessão por execução (anti-flood do gerador).
OBS_CAP = int(os.environ.get("CAPTURE_TAILER_OBS_CAP", "25"))
# Corte de recência (epoch ms) p/ DBs multi-sessão (mimo): o --since-hours filtra
# por ARQUIVO, mas um único .db tem centenas de sessões; sem corte por sessão a 1ª
# execução tentaria ingerir tudo de uma vez (flood). main() ajusta isto.
SESSION_CUTOFF_MS = 0

SCAN_GLOBS = {
    "antigravity": [
        str(HOME / ".gemini/antigravity-cli/brain/*/.system_generated/logs/transcript_full.jsonl"),
        str(HOME / ".gemini/tmp/*/chats/*.jsonl"),
    ],
    "hermes": str(HOME / ".hermes/sessions/*.jsonl"),
    "kimi": str(HOME / ".kimi/sessions/*/*/context.jsonl"),
    # Fonte oficial do Copilot: transcripts duráveis da IDE (+ fallback CLI db).
    "copilot": [
        str(HOME / ".config/Code/User/workspaceStorage/*/GitHub.copilot-chat/transcripts/*.jsonl"),
        str(HOME / ".copilot/session-store.db"),
    ],
    "openclaw": str(HOME / ".openclaw/tasks/runs.sqlite"),
    # DBs SQLite (tabelas message/part/session) → mesmo parser, badges separados.
    # mimo é CLI → timer. kilo e roo são gerenciados EXCLUSIVAMENTE pelo
    # capture-realtime (inotify + reparse); removê-los aqui elimina a corrida de
    # estado entre os dois processos que causava duplicação de prompts/sumários.
    "mimo": str(HOME / ".local/share/mimocode/mimocode.db"),
    # kilo e roo: NÃO incluir aqui — capturados pelo capture-realtime em tempo real.
}


def _src_mtime(p: Path) -> float:
    """mtime efetivo de uma fonte. SQLite em modo WAL grava no sidecar -wal (o .db
    só muda no checkpoint), então o mtime do .db fica horas atrasado. Considera o
    maior mtime entre o arquivo e os sidecars -wal/-shm para o filtro de recência
    não pular um DB com dados novos no WAL (ex.: kilo)."""
    mt = 0.0
    for cand in (p, Path(str(p) + "-wal"), Path(str(p) + "-shm")):
        try:
            mt = max(mt, cand.stat().st_mtime)
        except OSError:
            pass
    return mt


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


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text()) if STATE.exists() else {}
    except Exception:
        return {}


def save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2))


# --- parser antigravity -----------------------------------------------------
def parse_antigravity(path: Path):
    sid = next((p for p in path.parts if re.fullmatch(r"[0-9a-f-]{36}", p)), None)
    prompt, turns, last_text = None, [], None
    pending_user, pending_user_key = None, None
    user_seq = 0
    for ln in path.read_text(errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue

        # Gemini TMP chats: primeira linha é metadado de sessão.
        if d.get("kind") == "main" and d.get("sessionId"):
            sid = sid or str(d.get("sessionId"))
            continue

        t, idx = d.get("type"), d.get("step_index")

        # Antigravity transcript clássico.
        if t == "USER_INPUT":
            raw = d.get("content") or ""
            m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.S)
            prompt = (m.group(1) if m else raw).strip().strip('"')
        elif t == "PLANNER_RESPONSE" and d.get("tool_calls"):
            for j, c in enumerate(d["tool_calls"]):
                a = c.get("args", {}) if isinstance(c, dict) else {}
                turns.append({
                    "key": f"{idx}.{j}",
                    "tool_name": (c.get("name") if isinstance(c, dict) else None) or "AntigravityTool",
                    "tool_input": a,
                    "tool_response": a.get("toolSummary") or a.get("toolAction") or "ok",
                })
        elif t in ("VIEW_FILE", "LIST_DIRECTORY", "INVOKE_SUBAGENT"):
            content = (d.get("content") or "")[:4000]
            turns.append({
                "key": str(idx),
                "tool_name": "".join(w.capitalize() for w in t.split("_")),
                "tool_input": {"step": idx},
                "tool_response": content or "ok",
            })
            if content:
                last_text = content

        # Gemini CLI TMP transcript: type=user|gemini.
        elif t == "user":
            raw = _text(d.get("content") or "")
            # Remove bloco de contexto injetado por hooks para manter só o pedido real.
            cleaned = re.sub(r"<hook_context>.*?</hook_context>", "", raw, flags=re.S).strip()
            msg = cleaned or raw
            if msg:
                prompt = prompt or msg
                pending_user = msg
                user_seq += 1
                pending_user_key = d.get("id") or f"u:{user_seq}"
        elif t in ("gemini", "assistant", "model"):
            txt = _text(d.get("content") or "")
            if not txt:
                continue
            msg_id = d.get("id") or d.get("timestamp") or f"msg:{len(turns)}"
            turns.append({
                "key": f"tmp:{msg_id}",
                "tool_name": "Message",
                "tool_input": {"prompt": (pending_user or "")[:2000]},
                "tool_response": txt[:4000],
                "prompt_key": pending_user_key,
            })
            last_text = txt
            pending_user = None
            pending_user_key = None
    if not sid:
        return []
    return [{"sid": sid, "prompt": prompt, "turns": turns, "last": last_text}]


# --- parser genérico de chat role-based (hermes, kimi) ---------------------
def _text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        t = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("text"))
        return t or json.dumps(c, ensure_ascii=False)[:2000]
    return str(c or "")


def parse_chat_jsonl(path: Path):
    """Transcripts chat role-based: linhas {role: user|assistant|..., content}.
    session id = UUID no caminho (kimi) ou uuid5 estável do arquivo (hermes)."""
    import uuid as _uuid
    sid = next((p for p in path.parts if re.fullmatch(r"[0-9a-f-]{36}", p)), None) \
        or str(_uuid.uuid5(_uuid.NAMESPACE_URL, str(path)))
    prompt, turns, last_text, pending_user, n = None, [], None, None, 0
    pending_user_key = None
    user_seq = 0
    for ln in path.read_text(errors="ignore").splitlines():
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        role = d.get("role")
        if role == "user":
            txt = _text(d.get("content"))
            prompt = prompt or txt
            pending_user = txt
            user_seq += 1
            pending_user_key = f"u:{user_seq}"
        elif role == "assistant":
            txt = _text(d.get("content"))
            last_text = txt or last_text
            turns.append({
                "key": str(n), "tool_name": "Message",
                "tool_input": {"prompt": (pending_user or "")[:2000]},
                "tool_response": (txt or "ok")[:4000],
                "prompt_key": pending_user_key,
            })
            n += 1
            pending_user = None
            pending_user_key = None
    return [{"sid": sid, "prompt": prompt, "turns": turns, "last": last_text}]


def parse_cline(path: Path):
    """Formato Cline (Roo Code, Kilo Code — fork): VS Code globalStorage
    .../tasks/<uuid>/ui_messages.json = ARRAY JSON de mensagens. session id = uuid
    do diretório da task.

    Mapeamento de say/ask → papel:
      - 1º say:text (a task) e say:user_feedback  → prompt do usuário
      - demais say:text, say:completion_result, ask:followup → resposta do agent
      - api_req_*, error, command_output, checkpoint_saved… → ruído interno, ignora
    """
    sid = next((p for p in path.parts if re.fullmatch(r"[0-9a-f-]{36}", p)), path.parent.name)
    try:
        msgs = json.loads(path.read_text(errors="ignore"))
    except Exception:
        return []
    if not isinstance(msgs, list):
        return []
    prompt, turns, last_text = None, [], None
    pending_user, pending_user_key, seen_first_text, user_seq = None, None, False, 0

    def add_user(txt: str, ts):
        nonlocal prompt, pending_user, pending_user_key, user_seq
        txt = (txt or "").strip()
        if not txt:
            return
        prompt = prompt or txt
        pending_user = txt
        user_seq += 1
        pending_user_key = f"u:{ts or user_seq}"

    def add_assistant(txt: str, ts):
        nonlocal last_text, pending_user, pending_user_key
        txt = (txt or "").strip()
        if not txt:
            return
        last_text = txt
        turns.append({
            "key": f"m:{ts or len(turns)}", "tool_name": "Message",
            "tool_input": {"prompt": (pending_user or "")[:2000]},
            "tool_response": txt[:4000],
            "prompt_key": pending_user_key,
        })
        pending_user, pending_user_key = None, None

    for m in msgs:
        if not isinstance(m, dict):
            continue
        ts, typ, txt = m.get("ts"), m.get("type"), m.get("text") or ""
        if typ == "say":
            sub = m.get("say")
            if sub == "text":
                if not seen_first_text:          # 1ª mensagem de texto = task do usuário
                    seen_first_text = True
                    add_user(txt, ts)
                else:
                    add_assistant(txt, ts)
            elif sub == "user_feedback":
                add_user(txt, ts)
            elif sub == "completion_result":
                add_assistant(txt, ts)
        elif typ == "ask" and m.get("ask") == "followup":
            try:
                q = json.loads(txt).get("question") or txt
            except Exception:
                q = txt
            add_assistant(q, ts)
    if not prompt and not turns:
        return []
    return [{"sid": sid, "prompt": prompt, "turns": turns, "last": last_text}]


def parse_copilot_sqlite(db_path: Path):
    """Copilot CLI: ~/.copilot/session-store.db (SQLite). Uma DB, várias sessões
    na tabela `sessions`; turnos em `turns` (user_message, assistant_response)."""
    import sqlite3
    out = []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return out
    try:
        con.row_factory = sqlite3.Row
        for s in con.execute("SELECT id FROM sessions"):
            sid = str(s["id"])
            rows = con.execute(
                "SELECT turn_index, user_message, assistant_response FROM turns "
                "WHERE session_id=? ORDER BY turn_index", (sid,)).fetchall()
            if not rows:
                continue
            prompt = (rows[0]["user_message"] or "").strip() or "(sessão)"
            turns, last = [], None
            for r in rows:
                resp = (r["assistant_response"] or "").strip()
                last = resp or last
                turns.append({
                    "key": str(r["turn_index"]), "tool_name": "Message",
                    "tool_input": {"prompt": (r["user_message"] or "")[:2000]},
                    "tool_response": (resp or "ok")[:4000],
                })
            out.append({"sid": sid, "prompt": prompt, "turns": turns, "last": last})
    finally:
        con.close()
    return out


def parse_copilot_transcript(path: Path):
    """Copilot IDE: transcript JSONL em workspaceStorage/.../GitHub.copilot-chat/transcripts.

    Eventos relevantes:
      - session.start        -> sessionId
      - user.message         -> prompt/entrada do usuário
      - assistant.message    -> resposta do assistente
    """
    sid = path.stem
    prompt, turns, last_text, pending_user = None, [], None, None
    pending_user_key = None
    user_seq = 0
    current_turn_id = None
    turn_parts: list[str] = []

    def flush_turn(turn_id: str | None):
        nonlocal last_text, turn_parts
        if not turn_parts:
            return
        joined = "\n\n".join(part for part in turn_parts if part).strip()
        turn_parts = []
        if not joined:
            return
        key = turn_id or f"msg-{len(turns)}"
        turns.append({
            "key": f"ide:{key}",
            "tool_name": "CopilotTurn",
            "tool_input": {"prompt": (pending_user or "")[:2000]},
            "tool_response": joined[:4000],
            "prompt_key": pending_user_key,
        })
        last_text = joined
    for ln in path.read_text(errors="ignore").splitlines():
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue

        ev_type = d.get("type")
        data = d.get("data") or {}

        if ev_type == "session.start":
            sid = data.get("sessionId") or sid
            continue

        if ev_type == "user.message":
            flush_turn(current_turn_id)
            current_turn_id = None
            txt = _text(data.get("content"))
            if txt:
                prompt = prompt or txt
                pending_user = txt
                user_seq += 1
                pending_user_key = data.get("messageId") or d.get("id") or f"u:{user_seq}"
            continue

        if ev_type == "assistant.turn_start":
            flush_turn(current_turn_id)
            current_turn_id = data.get("turnId") or d.get("id")
            continue

        if ev_type == "assistant.turn_end":
            flush_turn(data.get("turnId") or current_turn_id)
            current_turn_id = None
            continue

        if ev_type != "assistant.message":
            continue

        txt = _text(data.get("content"))
        if not txt:
            txt = _text(data.get("reasoningText"))
        if not txt:
            continue

        tool_names = []
        for req in data.get("toolRequests") or []:
            if isinstance(req, dict):
                name = str(req.get("name") or "").strip()
                if name:
                    tool_names.append(name)
        if tool_names:
            txt = f"{txt}\n\n[tools] {', '.join(sorted(set(tool_names)))}"

        turn_parts.append(txt)

    flush_turn(current_turn_id)

    if not prompt and not turns:
        return []
    return [{"sid": sid, "prompt": prompt, "turns": turns, "last": last_text}]


def parse_copilot(path: Path):
    if path.suffix == ".db":
        return parse_copilot_sqlite(path)
    return parse_copilot_transcript(path)


def parse_mimo(db_path: Path):
    """Parser para DBs SQLite com o formato de tabelas `message`/`part`/`session`
    (coluna `data` em JSON). Reusado por ferramentas distintas só porque o esquema
    do arquivo é idêntico — NÃO implica relação entre elas; cada uma mantém seu
    próprio badge no viewer.
      mimo → ~/.local/share/mimocode/mimocode.db          (CLI)
      kilo → ~/snap/code/*/.local/share/kilo/kilo.db      (extensão VS Code)
    Sessões em `session`; mensagens em `message` (data.role); o texto real fica em
    `part` (data.type=text → data.text), ligado por part.message_id."""
    import sqlite3
    out = []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return out
    try:
        con.row_factory = sqlite3.Row
        # CRÍTICO: o mimocode.db AGREGA sessões importadas de outras ferramentas
        # (tabelas external_import/claude_import — ex.: 278 sessões do Claude Code).
        # Essas já são capturadas nativamente pela própria ferramenta de origem;
        # ingeri-las aqui as rotularia ERRADO como "mimo" (flood + badge errado).
        # Só ingerimos sessões NATIVAS do mimo (não presentes nas tabelas de import).
        imported = set()
        for tbl in ("external_import", "claude_import"):
            try:
                for r in con.execute(f"SELECT session_id FROM {tbl}"):
                    if r["session_id"]:
                        imported.add(str(r["session_id"]))
            except Exception:
                pass  # kilo não tem essas tabelas; mimo antigo idem
        # Recência por sessão: --since-hours filtra por ARQUIVO, mas um .db tem
        # dezenas de sessões → sem corte por sessão a 1ª execução tentaria ingerir
        # tudo (flood). SESSION_CUTOFF_MS=0 (standalone) = sem corte.
        sessions = [
            s for s in con.execute(
                "SELECT id, title FROM session WHERE COALESCE(time_updated,0) >= ? "
                "ORDER BY time_updated ASC", (SESSION_CUTOFF_MS,))
            if str(s["id"]) not in imported
        ]
        for s in sessions:
            sid = str(s["id"])
            msgs = con.execute(
                "SELECT id, json_extract(data,'$.role') AS role "
                "FROM message WHERE session_id=? ORDER BY time_created ASC", (sid,)
            ).fetchall()
            if not msgs:
                continue
            prompt, turns, last_text = None, [], None
            pending_user, pending_user_key, user_seq = None, None, 0
            skip_session = False
            for m in msgs:
                mid = str(m["id"])
                role = m["role"]
                parts = con.execute(
                    "SELECT json_extract(data,'$.text') AS txt FROM part "
                    "WHERE message_id=? AND json_extract(data,'$.type')='text' "
                    "ORDER BY time_created ASC", (mid,)).fetchall()
                txt = "\n\n".join((p["txt"] or "").strip() for p in parts if p["txt"]).strip()
                if not txt:
                    continue
                if role == "user":
                    if prompt is None and txt.lstrip().startswith("<system-reminder>"):
                        # Sessão automática (dream cycle, checkpoint-writer, etc.)
                        skip_session = True
                        break
                    prompt = prompt or txt
                    pending_user = txt
                    user_seq += 1
                    pending_user_key = f"u:{mid}"
                elif role == "assistant":
                    last_text = txt
                    turns.append({
                        "key": f"m:{mid}", "tool_name": "Message",
                        "tool_input": {"prompt": (pending_user or "")[:2000]},
                        "tool_response": txt[:4000],
                        "prompt_key": pending_user_key,
                    })
                    pending_user, pending_user_key = None, None
            if not skip_session and (prompt or turns):
                out.append({"sid": sid, "prompt": prompt, "turns": turns, "last": last_text})
    finally:
        con.close()
    return out


def parse_openclaw(db_path: Path):
    """OpenClaw: captura de task_runs em ~/.openclaw/tasks/runs.sqlite.

    Mapeamento para claude-mem:
      - sid   -> task_id
      - prompt -> coluna task
      - observação -> progress_summary / terminal_summary / status
    """
    import sqlite3

    out = []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return out
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT task_id, task, status, progress_summary, terminal_summary, "
            "created_at, last_event_at, runtime, task_kind "
            "FROM task_runs ORDER BY created_at ASC"
        ).fetchall()
    except Exception:
        con.close()
        return out

    for r in rows:
        sid = (r["task_id"] or "").strip()
        if not sid:
            continue
        prompt = (r["task"] or "").strip() or "(task openclaw)"
        summary = (r["progress_summary"] or "").strip()
        terminal = (r["terminal_summary"] or "").strip()
        status = (r["status"] or "").strip() or "unknown"
        response = summary or terminal or f"status={status}"

        key = str(r["last_event_at"] or r["created_at"] or sid)
        turns = [{
            "key": f"run:{key}",
            "tool_name": "OpenClawTask",
            "tool_input": {
                "prompt": prompt[:2000],
                "status": status,
                "runtime": r["runtime"],
                "task_kind": r["task_kind"],
            },
            "tool_response": response[:4000],
        }]
        out.append({"sid": sid, "prompt": prompt, "turns": turns, "last": response})

    con.close()
    return out


PARSERS = {
    "antigravity": parse_antigravity,
    "hermes": parse_chat_jsonl,
    "kimi": parse_chat_jsonl,
    "copilot": parse_copilot,
    "openclaw": parse_openclaw,
    "mimo": parse_mimo,
    "kilo": parse_mimo,
    "roo": parse_cline,
}


def ingest(platform: str, sess: dict, state: dict) -> int:
    sid = sess.get("sid")
    prompt, turns, last_text = sess.get("prompt"), sess.get("turns") or [], sess.get("last")
    if not sid or (not prompt and not turns):
        return 0
    skey = f"{platform}:{sid}"
    rec = state.setdefault(skey, {
        "inited": False,
        "keys": [],
        "prompt_keys": [],
        "prompt_recent": {},
        "prompt_recent_texts": [],
    })
    if "prompt_keys" not in rec or not isinstance(rec.get("prompt_keys"), list):
        rec["prompt_keys"] = []
    if "prompt_recent" not in rec or not isinstance(rec.get("prompt_recent"), dict):
        rec["prompt_recent"] = {}
    if "prompt_recent_texts" not in rec or not isinstance(rec.get("prompt_recent_texts"), list):
        rec["prompt_recent_texts"] = []
    done = set(rec["keys"])
    prompt_done = set(rec.get("prompt_keys") or [])
    prompt_recent = rec.get("prompt_recent") or {}
    prompt_recent_texts = rec.get("prompt_recent_texts") or []
    now_ts = int(time.time())
    recent_ttl = 180
    for h, ts in list(prompt_recent.items()):
        try:
            if now_ts - int(ts) > recent_ttl:
                prompt_recent.pop(h, None)
        except Exception:
            prompt_recent.pop(h, None)
    compact_recent_texts = []
    for entry in prompt_recent_texts:
        if not isinstance(entry, dict):
            continue
        ptxt = str(entry.get("prompt") or "")
        try:
            pts = int(entry.get("ts") or 0)
        except Exception:
            pts = 0
        if ptxt and (now_ts - pts) <= recent_ttl:
            compact_recent_texts.append({"prompt": ptxt, "ts": pts})
    prompt_recent_texts = compact_recent_texts[-10:]
    new = [t for t in turns if t["key"] not in done]
    # Anti-flood: nunca despeja a sessão inteira de uma vez (uma sessão grande de
    # copilot/antigravity pode ter centenas de turns → afoga o gerador). Manda no
    # máximo OBS_CAP por execução; o resto entra nas próximas (state incremental).
    if len(new) > OBS_CAP:
        print(f"  ⏳ {platform}:{sid[:12]}: {len(new)} turns novos; enviando {OBS_CAP} "
              f"(resto nas próximas execuções)")
        new = new[:OBS_CAP]
    if rec["inited"] and not new:
        return 0

    if not rec["inited"]:
        _post("/api/sessions/init", {
            "contentSessionId": sid, "project": PROJECT, "platformSource": platform,
            "prompt": prompt or "(sessão)", "customTitle": f"[{platform}] {(prompt or '')[:60]}",
        })
        rec["inited"] = True

    sent = 0
    for t in new:
        # Inicializa prompt apenas uma vez por chave de prompt do usuário,
        # evitando duplicar a mesma mensagem quando há múltiplos eventos
        # de assistant/tool para o mesmo input do usuário.
        turn_prompt = ""
        if isinstance(t.get("tool_input"), dict):
            turn_prompt = str(t["tool_input"].get("prompt") or "").strip()
        prompt_key = str(t.get("prompt_key") or "").strip()
        norm_prompt = re.sub(r"\s+", " ", (turn_prompt or "").strip()).lower()
        prompt_hash = hashlib.sha1(norm_prompt.encode("utf-8", errors="ignore")).hexdigest() if norm_prompt else ""
        recently_seen_same_prompt = bool(prompt_hash and prompt_hash in prompt_recent)
        recently_seen_similar_prompt = False
        if norm_prompt and prompt_recent_texts:
            for item in prompt_recent_texts:
                prev = item.get("prompt") or ""
                if not prev:
                    continue
                # Copilot pode gerar eventos user.message quase idênticos com IDs distintos;
                # bloqueia replay semânticamente equivalente em janela curta.
                if difflib.SequenceMatcher(a=prev, b=norm_prompt).ratio() >= 0.985:
                    recently_seen_similar_prompt = True
                    break

        if (
            turn_prompt
            and prompt_key
            and prompt_key not in prompt_done
            and not recently_seen_same_prompt
            and not recently_seen_similar_prompt
        ):
            _post("/api/sessions/init", {
                "contentSessionId": sid,
                "project": PROJECT,
                "platformSource": platform,
                "prompt": turn_prompt,
                "customTitle": f"[{platform}] {(turn_prompt or '')[:60]}",
            })
            rec["prompt_keys"].append(prompt_key)
            prompt_done.add(prompt_key)
            if prompt_hash:
                prompt_recent[prompt_hash] = now_ts
            prompt_recent_texts.append({"prompt": norm_prompt, "ts": now_ts})
            rec["prompt_recent_texts"] = prompt_recent_texts[-10:]

        tn = (t["tool_name"] or "Tool").strip() or "Tool"
        tool_use_id = f"{platform}:{sid}:{t['key']}"
        obs_res = _post("/api/sessions/observations", {
            "contentSessionId": sid, "tool_name": tn,
            "tool_input": t["tool_input"], "tool_response": {"result": t["tool_response"]},
            "platformSource": platform, "cwd": str(Path.cwd()),
            "tool_use_id": tool_use_id,
        })
        if obs_res.get("error") or obs_res.get("stored") is False:
            # Não marca como processado quando a API rejeita (ex.: conflito de platformSource).
            continue
        rec["keys"].append(t["key"])
        sent += 1

    if sent:
        _post("/api/sessions/summarize", {
            "contentSessionId": sid, "platformSource": platform,
            "last_assistant_message": last_text or prompt or "sessão concluída",
        })
    print(f"  ✓ {platform}:{sid[:12]} → {sent} nova(s)")
    return sent


def _acquire_lock():
    """Garante instância única (evita corrida no state-file e ingestão duplicada
    quando o timer dispara enquanto uma execução anterior ainda roda).

    Usa lock file com PID: escreve o PID no arquivo e verifica se o processo
    ainda está vivo. Mais robusto que fcntl.flock() que tem problemas com
    herança de FD e liberação assíncrona pelo kernel."""
    import fcntl as _fcntl
    lock_path = DATA_DIR / "tailer.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Tenta abrir com flock primeiro (rápido, cobre 99% dos casos)
    try:
        fh = open(lock_path, "r+")
    except FileNotFoundError:
        fh = open(lock_path, "w")

    try:
        _fcntl.flock(fh, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
    except BlockingIOError:
        # Flock ocupado — verifica se o PID no arquivo ainda está vivo
        try:
            fh.seek(0)
            stale_pid = int(fh.read().strip() or 0)
        except (ValueError, OSError):
            stale_pid = 0
        if stale_pid > 1:
            try:
                os.kill(stale_pid, 0)  # signal 0 = check if exists
            except OSError:
                # Processo morto — rouba o lock
                fh.close()
                fh = open(lock_path, "w")
                _fcntl.flock(fh, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                print(f"  🔓 lock órpham do PID {stale_pid} liberado")
            else:
                print(f"⊘ outra instância do tailer já está rodando (PID {stale_pid}) — "
                      "saindo (sem perda; transcripts são duráveis, próxima execução "
                      "pega o que faltar).")
                sys.exit(0)
        else:
            print("⊘ outra instância do tailer já está rodando — saindo (sem perda; "
                  "transcripts são duráveis, próxima execução pega o que faltar).")
            sys.exit(0)

    # Escreve PID atual no arquivo
    fh.seek(0)
    fh.write(str(os.getpid()))
    fh.truncate()
    fh.flush()
    return fh  # mantém aberto enquanto o processo viver


def main() -> int:
    # Lock é gerenciado externamente pelo wrapper shell (flock) quando
    # executado via systemd timer. Quando rodado manualmente, o próprio
    # sistema já garante singleton (usuário não vai rodar 2x em paralelo).
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=list(PARSERS),
                    help="plataforma específica; omita com --all")
    ap.add_argument("--all", action="store_true", help="todas as plataformas com transcript")
    ap.add_argument("--source")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--since-hours", type=float, default=24.0,
                    help="no --scan, só transcripts modificados nas últimas N horas (evita bulk-ingest)")
    args = ap.parse_args()
    if not args.all and not args.platform:
        ap.error("informe --platform <p> ou --all")
    if not worker_alive():
        # worker fora (ex.: reiniciando) não é falha do tailer — skip gracioso;
        # transcripts são duráveis, a próxima execução do timer recupera.
        print(f"⊘ worker fora em {BASE} — pulando (próxima execução recupera)")
        return 0

    import time
    cutoff = time.time() - args.since_hours * 3600
    # Corte por-sessão (epoch ms) p/ DBs SQLite multi-sessão (mimo/kilo): não
    # despeja sessões antigas de uma vez. Mesma janela do filtro de arquivo.
    global SESSION_CUTOFF_MS
    SESSION_CUTOFF_MS = int(cutoff * 1000)
    # --all usa SCAN_GLOBS (não PARSERS): plataformas sem entry aqui são gerenciadas
    # por outro processo (ex.: kilo/roo → capture-realtime). PARSERS mantém parsers
    # de todas as plataformas para uso com --platform explícito + --source.
    platforms = list(SCAN_GLOBS) if args.all else [args.platform]
    state = load_state()
    total = 0

    # Caminho único: o ingest completo (abaixo) captura prompt + resposta +
    # sumário de TODAS as plataformas (incl. copilot), com o mesmo
    # platformSource/badge. Sem fase de "realtime só-prompt" separada.
    for plat in platforms:
        if args.source and not args.all:
            sources = [Path(args.source)]
        else:
            patterns = SCAN_GLOBS[plat]
            if isinstance(patterns, str):
                patterns = [patterns]
            found = []
            for pattern in patterns:
                found.extend(glob.glob(pattern))
            sources = [Path(p) for p in found
                       if Path(p).is_file() and _src_mtime(Path(p)) >= cutoff]
        for s in sources:
            if not s.is_file():
                continue
            try:
                sessions = PARSERS[plat](s)
            except Exception as exc:
                print(f"  ⚠ {plat}:{s.name}: parse falhou ({exc})")
                continue
            for sess in sessions:
                ingest_platform = plat
                # Gemini CLI headless grava em ~/.gemini/tmp/<project>/chats/*.jsonl
                # e usa platformSource nativo gemini-cli no worker.
                sp = str(s)
                if plat == "antigravity" and "/.gemini/tmp/" in sp and "/chats/" in sp:
                    ingest_platform = "gemini-cli"
                total += ingest(ingest_platform, sess, state)
    save_state(state)
    print(f"total: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
