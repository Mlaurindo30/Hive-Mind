#!/usr/bin/env python3
"""Parser DEDICADO do OpenClaw.

Fonte: ~/.openclaw/tasks/runs.sqlite (SQLite — tabela task_runs).
Mapeamento: sid=task_id, prompt=task, observação=progress/terminal_summary/status.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def parse(db_path: Path):
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
        turns = [{
            "tool_name": "OpenClawTask",
            "tool_input": {
                "prompt": prompt[:2000], "status": status,
                "runtime": r["runtime"], "task_kind": r["task_kind"],
            },
            "tool_response": response[:4000],
        }]
        out.append({"sid": sid, "prompt": prompt, "turns": turns, "last": response})
    con.close()
    return out
