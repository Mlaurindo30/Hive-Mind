#!/usr/bin/env python3
"""Parser DEDICADO do GitHub Copilot.

Fontes:
  • IDE: ~/.config/Code/User/workspaceStorage/*/GitHub.copilot-chat/transcripts/*.jsonl
         (JSONL APPEND-ONLY, 1 arquivo por sessão) — caminho principal.
  • CLI: ~/.copilot/session-store.db (SQLite, fallback).
"""
from __future__ import annotations

import json
from pathlib import Path

from capture_core import _text, project_from_cwd


def _workspace_cwd(path: Path) -> str | None:
    """cwd da sessão = pasta do workspace do VS Code. O transcript fica em
    workspaceStorage/<hash>/GitHub.copilot-chat/transcripts/<sid>.jsonl; o
    workspace.json irmão (3 níveis acima) mapeia o hash → pasta real."""
    try:
        ws = path.parents[2] / "workspace.json"   # <hash>/workspace.json
        folder = (json.loads(ws.read_text()).get("folder") or "")
        return folder.replace("file://", "") or None
    except Exception:
        return None


def _parse_transcript(path: Path):
    sid = path.stem
    cwd = _workspace_cwd(path)
    prompt, turns, last_text, pending_user = None, [], None, None
    current_turn_id = None
    turn_parts: list[str] = []

    def flush(turn_id):
        nonlocal last_text, turn_parts
        if not turn_parts:
            return
        joined = "\n\n".join(p for p in turn_parts if p).strip()
        turn_parts = []
        if not joined:
            return
        turns.append({
            "tool_name": "CopilotTurn",
            "tool_input": {"prompt": (pending_user or "")[:2000]},
            "tool_response": joined[:4000],
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
        ev, data = d.get("type"), d.get("data") or {}
        if ev == "session.start":
            sid = data.get("sessionId") or sid
        elif ev == "user.message":
            flush(current_turn_id); current_turn_id = None
            txt = _text(data.get("content"))
            if txt:
                prompt = prompt or txt
                pending_user = txt
        elif ev == "assistant.turn_start":
            flush(current_turn_id); current_turn_id = data.get("turnId") or d.get("id")
        elif ev == "assistant.turn_end":
            flush(data.get("turnId") or current_turn_id); current_turn_id = None
        elif ev == "assistant.message":
            txt = _text(data.get("content")) or _text(data.get("reasoningText"))
            if not txt:
                continue
            names = [str(r.get("name") or "").strip()
                     for r in (data.get("toolRequests") or []) if isinstance(r, dict)]
            names = [n for n in names if n]
            if names:
                txt = f"{txt}\n\n[tools] {', '.join(sorted(set(names)))}"
            turn_parts.append(txt)
    flush(current_turn_id)
    if not prompt and not turns:
        return []
    return [{"sid": sid, "prompt": prompt, "turns": turns, "last": last_text,
             "project": project_from_cwd(cwd), "cwd": cwd}]


def _parse_sqlite(db_path: Path):
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
                    "tool_name": "Message",
                    "tool_input": {"prompt": (r["user_message"] or "")[:2000]},
                    "tool_response": (resp or "ok")[:4000],
                })
            out.append({"sid": sid, "prompt": prompt, "turns": turns, "last": last})
    finally:
        con.close()
    return out


def parse(path: Path):
    return _parse_sqlite(path) if path.suffix == ".db" else _parse_transcript(path)
