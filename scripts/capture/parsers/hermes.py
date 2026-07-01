#!/usr/bin/env python3
"""Parser DEDICADO do Hermes (state.db — formato pós-v0.9).

Fonte: ~/.hermes/state.db (SQLite)
Tabelas:
  sessions  — id, source ('cli'|'cron'|…), model, started_at (epoch secs float), cwd
  messages  — session_id, role, content, timestamp
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import capture_core as core

HERMES_PROJECT = "hermes"

_NOTE_PREFIX = "[Note:"


def _strip_note(text: str) -> str:
    """Remove Hermes-injected model-switch notes that precede the real user message."""
    if not text.startswith(_NOTE_PREFIX):
        return text
    end = text.find("]")
    if end == -1:
        return text
    return text[end + 1:].lstrip()


def parse(db_path: Path):
    out = []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return out
    try:
        con.row_factory = sqlite3.Row
        cutoff_secs = core.SESSION_CUTOFF_MS / 1000.0
        sessions = con.execute(
            "SELECT id, cwd FROM sessions"
            " WHERE started_at >= ? AND source = 'cli'"
            " ORDER BY started_at ASC",
            (cutoff_secs,),
        ).fetchall()
        for sess in sessions:
            sid = sess["id"]
            rows = con.execute(
                "SELECT role, content FROM messages"
                " WHERE session_id = ? AND active = 1"
                " ORDER BY timestamp ASC",
                (sid,),
            ).fetchall()
            prompt, turns, last_text, pending_user = None, [], None, None
            for row in rows:
                role = row["role"]
                raw = (row["content"] or "").strip()
                if role == "user":
                    txt = _strip_note(raw)
                    if not txt:
                        continue
                    prompt = prompt or txt
                    pending_user = txt
                elif role == "assistant":
                    last_text = raw or last_text
                    turns.append({
                        "tool_name": "Message",
                        "tool_input": {"prompt": (pending_user or "")[:2000]},
                        "tool_response": (raw or "ok")[:4000],
                    })
                    pending_user = None
            if prompt or turns:
                out.append({
                    "sid": sid,
                    "prompt": prompt,
                    "turns": turns,
                    "last": last_text,
                    "project": HERMES_PROJECT,
                    "cwd": sess["cwd"],
                })
    finally:
        con.close()
    return out
