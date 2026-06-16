#!/usr/bin/env python3
"""Parser DEDICADO do Kilo Code (extensão VS Code).

Fonte: ~/snap/code/*/.local/share/kilo/kilo.db (SQLite — tabelas session/message/part).
Esquema: idêntico ao do mimo (session/message/part, texto em part.data.text), mas
         o Kilo é uma ferramenta SEPARADA e NÃO tem as tabelas de import nem os
         subagentes internos do mimo — por isso este módulo é independente e limpo
         (sem exclusão de import, sem filtro de <system-reminder>).

Mantê-lo separado do mimo garante que uma mudança no Kilo nunca afete o mimo e
vice-versa, mesmo o esquema de arquivo sendo o mesmo.
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
        sessions = con.execute(
            "SELECT id, title FROM session WHERE COALESCE(time_updated,0) >= ? "
            "ORDER BY time_updated ASC", (core.SESSION_CUTOFF_MS,)).fetchall()
        for s in sessions:
            sid = str(s["id"])
            msgs = con.execute(
                "SELECT id, json_extract(data,'$.role') AS role "
                "FROM message WHERE session_id=? ORDER BY time_created ASC", (sid,)
            ).fetchall()
            if not msgs:
                continue
            prompt, turns, last_text, pending_user = None, [], None, None
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
            if prompt or turns:
                out.append({"sid": sid, "prompt": prompt, "turns": turns, "last": last_text})
    finally:
        con.close()
    return out
