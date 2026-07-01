#!/usr/bin/env python3
"""Parser DEDICADO do OpenClaw.

Fonte: ~/.openclaw/tasks/runs.sqlite (SQLite — tabela task_runs).
Mapeamento: sid=task_id, prompt=task, observação=progress/terminal_summary/status.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import capture_core as core


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def _col(row: sqlite3.Row, cols: set[str], *names: str, default: str = "") -> str:
    for name in names:
        if name in cols:
            return (row[name] or "").strip()
    return default


def parse(db_path: Path):
    out = []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return out
    try:
        con.row_factory = sqlite3.Row
        cols = _columns(con, "task_runs")
        if not cols:
            con.close()
            return out

        # Colunas mínimas obrigatórias; colunas opcionais degradam graciosamente.
        required = {"task_id", "task", "status", "created_at"}
        missing = required - cols
        if missing:
            raise ValueError(f"task_runs schema changed — colunas ausentes: {missing}")

        ts_col = "last_event_at" if "last_event_at" in cols else "created_at"
        select_cols = ", ".join(
            c for c in (
                "task_id", "task", "status",
                "progress_summary", "terminal_summary",
                "created_at", "last_event_at", "runtime", "task_kind",
            )
            if c in cols
        )
        rows = con.execute(
            f"SELECT {select_cols} FROM task_runs "
            f"WHERE COALESCE({ts_col}, created_at) >= ? "
            "ORDER BY created_at ASC",
            (core.SESSION_CUTOFF_MS,),
        ).fetchall()
    except Exception:
        con.close()
        raise
    for r in rows:
        sid = _col(r, cols, "task_id")
        if not sid:
            continue
        prompt = _col(r, cols, "task") or "(task openclaw)"
        summary = _col(r, cols, "progress_summary")
        terminal = _col(r, cols, "terminal_summary")
        status = _col(r, cols, "status") or "unknown"
        response = summary or terminal or f"status={status}"
        turns = [{
            "tool_name": "OpenClawTask",
            "tool_input": {
                "prompt": prompt[:2000],
                "status": status,
                "runtime": _col(r, cols, "runtime"),
                "task_kind": _col(r, cols, "task_kind"),
            },
            "tool_response": response[:4000],
        }]
        out.append({"sid": sid, "prompt": prompt, "turns": turns, "last": response})
    con.close()
    return out
