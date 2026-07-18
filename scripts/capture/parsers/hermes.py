#!/usr/bin/env python3
"""Parser dedicado do Hermes CLI e Desktop (state.db pós-v0.9).

Fonte:
  Windows: %LOCALAPPDATA%/hermes/state.db
  POSIX:   ~/.hermes/state.db

A conexão SQLite é estritamente read-only e acompanha o WAL ativo. Somente
sessões top-level (``cli`` e ``desktop``) entram no pipeline; subagentes e
fontes internas permanecem excluídos.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import capture_core as core

_NOTE_PREFIX = "[Note:"
_TOP_LEVEL_SOURCES = ("cli", "desktop")


def _strip_note(text: str) -> str:
    """Remove apenas uma nota completa que preceda a mensagem real."""
    if not text.startswith(_NOTE_PREFIX):
        return text
    end = text.find("]")
    if end == -1:
        return text
    return text[end + 1:].lstrip()


def _readonly_uri(db_path: Path) -> str:
    return f"{db_path.resolve().as_uri()}?mode=ro"


def parse(db_path: Path) -> list[dict]:
    sessions_out: list[dict] = []
    try:
        connection = sqlite3.connect(
            _readonly_uri(db_path),
            uri=True,
            timeout=5,
        )
    except (OSError, sqlite3.Error, ValueError):
        return sessions_out

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        cutoff_secs = core.SESSION_CUTOFF_MS / 1000.0
        sessions = connection.execute(
            "SELECT id, source, model, started_at, cwd, git_branch, git_repo_root"
            " FROM sessions"
            " WHERE started_at >= ? AND source IN (?, ?)"
            " ORDER BY started_at ASC, id ASC",
            (cutoff_secs, *_TOP_LEVEL_SOURCES),
        ).fetchall()

        for session_row in sessions:
            sid = str(session_row["id"])
            rows = connection.execute(
                "SELECT id, role, content, timestamp FROM messages"
                " WHERE session_id = ? AND active = 1"
                " ORDER BY timestamp ASC, id ASC",
                (sid,),
            ).fetchall()

            prompts: list[str] = []
            prompt_events: list[dict] = []
            turns: list[dict] = []
            messages: list[dict] = []
            pending_user: str | None = None
            last_text: str | None = None

            for row in rows:
                role = str(row["role"] or "").strip()
                content = str(row["content"] or "").strip()
                timestamp = row["timestamp"]
                if not role or not content:
                    continue
                if role == "user":
                    content = _strip_note(content)
                    if not content:
                        continue
                    prompts.append(content)
                    prompt_events.append({
                        "event_id": f"{sid}:message:{row['id']}",
                        "content": content,
                        "timestamp": timestamp,
                        "source_position": f"messages:id:{row['id']}",
                    })
                    pending_user = content
                elif role == "assistant":
                    last_text = content
                    turns.append({
                        "tool_name": "Message",
                        "tool_input": {"prompt": (pending_user or "")[:2000]},
                        "tool_response": content,
                        "timestamp": timestamp,
                    })
                    pending_user = None

                messages.append({
                    "role": role,
                    "content": content,
                    "timestamp": timestamp,
                })

            if not prompts and not turns and not messages:
                continue

            source = str(session_row["source"])
            sessions_out.append({
                "sid": sid,
                "source": source,
                "surface": source,
                "model": session_row["model"],
                "started_at": session_row["started_at"],
                "cwd": session_row["cwd"],
                "git_branch": session_row["git_branch"],
                "git_repo_root": session_row["git_repo_root"],
                "prompt": prompts[0] if prompts else None,
                "prompts": prompts,
                "prompt_events": prompt_events,
                "turns": turns,
                "messages": messages,
                "last": last_text,
            })
    except sqlite3.Error:
        return []
    finally:
        connection.close()

    return sessions_out
