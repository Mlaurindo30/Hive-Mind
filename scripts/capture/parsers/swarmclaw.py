#!/usr/bin/env python3
"""Parser DEDICADO do SwarmClaw.

Fonte: ~/.swarmclaw/data/swarmclaw.db (SQLite)
Tabelas:
  sessions       — metadados de cada sessão (id, data JSON: lastActiveAt, name, agentId)
  runtime_runs   — cada turno de conversa (data JSON: messagePreview, resultPreview,
                   queuedAt, status, sessionId)

Sessões ficam em `.swarmclaw/workspace/` como CWD, mas o projeto deve ser 'swarmclaw'
— não derivado do basename (que seria 'workspace').
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import capture_core as core

SWARMCLAW_PROJECT = "swarmclaw"


def parse(db_path: Path):
    out = []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return out
    try:
        con.row_factory = sqlite3.Row

        sessions = con.execute(
            "SELECT id, json_extract(data,'$.name') AS name,"
            "       json_extract(data,'$.agentId') AS agent_id,"
            "       json_extract(data,'$.lastActiveAt') AS last_active,"
            "       json_extract(data,'$.cwd') AS cwd"
            " FROM sessions"
            " WHERE COALESCE(json_extract(data,'$.lastActiveAt'), 0) >= ?"
            " ORDER BY json_extract(data,'$.lastActiveAt') ASC",
            (core.SESSION_CUTOFF_MS,),
        ).fetchall()

        for sess in sessions:
            sid = str(sess["id"])
            name = sess["name"] or "swarmclaw"

            runs = con.execute(
                "SELECT json_extract(data,'$.messagePreview') AS input,"
                "       json_extract(data,'$.resultPreview')  AS result,"
                "       json_extract(data,'$.queuedAt')       AS queued_at,"
                "       json_extract(data,'$.status')         AS status"
                " FROM runtime_runs"
                " WHERE json_extract(data,'$.sessionId') = ?"
                "   AND json_extract(data,'$.internal') IS NOT 1"
                " ORDER BY json_extract(data,'$.queuedAt') ASC",
                (sid,),
            ).fetchall()

            prompt, turns, last_text, pending_user = None, [], None, None
            for run in runs:
                user_txt = (run["input"] or "").strip()
                resp_txt = (run["result"] or "").strip()
                if not user_txt:
                    continue
                prompt = prompt or user_txt
                pending_user = user_txt
                if resp_txt:
                    last_text = resp_txt
                    turns.append({
                        "tool_name": "Message",
                        "tool_input": {"prompt": user_txt[:2000]},
                        "tool_response": resp_txt[:4000],
                    })
                    pending_user = None

            if prompt or turns:
                out.append({
                    "sid": sid,
                    "prompt": prompt,
                    "turns": turns,
                    "last": last_text,
                    "project": SWARMCLAW_PROJECT,
                    "cwd": sess["cwd"],
                })
    finally:
        con.close()
    return out
