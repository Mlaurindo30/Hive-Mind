#!/usr/bin/env python3
"""Parser DEDICADO do MiMo Code (CLI).

Fonte: ~/.local/share/mimocode/mimocode.db (SQLite — tabelas session/message/part).
Esquema: sessões em `session`; mensagens em `message` (data.role); o texto real em
         `part` (data.type=text → data.text), ligado por part.message_id.

Particularidades EXCLUSIVAS do mimo (por isso é um módulo separado do kilo, que
usa o MESMO esquema de tabelas mas NÃO tem estas quirks):
  • o mimocode.db AGREGA sessões importadas de outras ferramentas nas tabelas
    external_import / claude_import → essas são excluídas (senão entrariam com o
    badge errado "mimo");
  • o mimo roda subagentes internos (checkpoint-writer / dream cycle) cujo 1º
    texto do usuário começa com <system-reminder> → essas sessões são puladas.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import capture_core as core


def parse(db_path: Path):
    out = []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return out
    try:
        con.row_factory = sqlite3.Row
        imported = set()
        for tbl in ("external_import", "claude_import"):
            try:
                for r in con.execute(f"SELECT session_id FROM {tbl}"):
                    if r["session_id"]:
                        imported.add(str(r["session_id"]))
            except Exception:
                pass
        sessions = [
            s for s in con.execute(
                "SELECT id, title FROM session WHERE COALESCE(time_updated,0) >= ? "
                "ORDER BY time_updated ASC", (core.SESSION_CUTOFF_MS,))
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
            prompt, turns, last_text, pending_user = None, [], None, None
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
                        skip_session = True
                        break
                    prompt = prompt or txt
                    pending_user = txt
                elif role == "assistant":
                    last_text = txt
                    turns.append({
                        "tool_name": "Message",
                        "tool_input": {"prompt": (pending_user or "")[:2000]},
                        "tool_response": txt[:4000],
                    })
                    pending_user = None
            if not skip_session and (prompt or turns):
                out.append({"sid": sid, "prompt": prompt, "turns": turns, "last": last_text})
    finally:
        con.close()
    return out
