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
from urllib.parse import unquote, urlsplit

from capture_core import text_content


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _quoted_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _session_identity_columns(connection) -> dict[str, str]:
    """Return available Copilot session columns by their normalized meaning."""
    available = {
        str(row["name"]).casefold(): str(row["name"])
        for row in connection.execute("PRAGMA table_info(sessions)")
    }
    aliases = {
        "cwd": ("cwd",),
        "repository": ("repository", "git_repo_root", "repo_root"),
        "branch": ("branch", "git_branch"),
        "host_type": ("host_type",),
    }
    resolved: dict[str, str] = {}
    for normalized, candidates in aliases.items():
        column = next((available[name] for name in candidates if name in available), None)
        if column is not None:
            resolved[normalized] = column
    return resolved


def _host_surface(host_type: str | None) -> tuple[str, str]:
    host = (host_type or "cli").casefold()
    source = f"copilot-{host}"
    if host in {"vscode", "visual-studio-code", "ide", "editor"}:
        return source, "ide"
    if host == "desktop":
        return source, "desktop"
    return source, "cli"


def _workspace_cwd(path: Path) -> str | None:
    """cwd da sessão = pasta do workspace do VS Code. O transcript fica em
    workspaceStorage/<hash>/GitHub.copilot-chat/transcripts/<sid>.jsonl; o
    workspace.json irmão (3 níveis acima) mapeia o hash → pasta real."""
    try:
        ws = next(
            (parent / "workspace.json" for parent in path.parents if (parent / "workspace.json").is_file()),
            None,
        )
        if ws is None:
            return None
        folder = (json.loads(ws.read_text()).get("folder") or "")
        parsed = urlsplit(folder)
        if parsed.scheme.lower() != "file":
            return folder or None
        uri_path = unquote(parsed.path)
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            host = unquote(parsed.netloc)
            share = uri_path.replace("/", "\\").lstrip("\\")
            return f"\\\\{host}\\{share}" if share else f"\\\\{host}"
        if len(uri_path) >= 4 and uri_path[0] == "/" and uri_path[2] == ":":
            uri_path = uri_path[1:]
        return uri_path or None
    except Exception:
        return None


def _parse_chat_session(path: Path):
    """Parse current VS Code ``chatSessions`` patch-log JSONL."""
    sid = path.stem
    cwd = _workspace_cwd(path)
    requests: list[dict] = []
    for line in path.read_text(errors="ignore").splitlines():
        try:
            record = json.loads(line)
        except (TypeError, ValueError):
            continue
        kind, key, value = record.get("kind"), record.get("k"), record.get("v")
        if kind == 0 and isinstance(value, dict):
            sid = str(value.get("sessionId") or sid)
            if isinstance(value.get("requests"), list):
                requests.extend(item for item in value["requests"] if isinstance(item, dict))
        elif kind == 2 and key == ["requests"] and isinstance(value, list):
            requests.extend(item for item in value if isinstance(item, dict))

    prompts: list[str] = []
    prompt_events: list[dict] = []
    seen_ids: set[str] = set()
    for index, request in enumerate(requests):
        message = request.get("message") or {}
        text = _clean_text(message.get("text") if isinstance(message, dict) else None)
        if not text:
            continue
        event_id = str(request.get("requestId") or index)
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        prompts.append(text)
        prompt_events.append({
            "event_id": event_id,
            "content": text,
            "timestamp": request.get("timestamp"),
            "source_position": f"{path.name}:request:{event_id}",
        })
    if not prompts:
        return []
    return [{
        "sid": sid,
        "prompt": prompts[0],
        "prompts": prompts,
        "prompt_events": prompt_events,
        "turns": [],
        "last": None,
        "source": "copilot-vscode",
        "surface": "ide",
        "official_workspace": cwd,
        "cwd": cwd,
    }]


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
            txt = text_content(data.get("content"))
            if txt:
                prompt = prompt or txt
                pending_user = txt
        elif ev == "assistant.turn_start":
            flush(current_turn_id); current_turn_id = data.get("turnId") or d.get("id")
        elif ev == "assistant.turn_end":
            flush(data.get("turnId") or current_turn_id); current_turn_id = None
        elif ev == "assistant.message":
            txt = text_content(data.get("content")) or text_content(data.get("reasoningText"))
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
             "source": "vscode", "surface": "ide",
             "official_workspace": cwd, "cwd": cwd}]


def _parse_sqlite(db_path: Path):
    import sqlite3
    out = []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return out
    try:
        con.row_factory = sqlite3.Row
        identity_columns = _session_identity_columns(con)
        select_columns = ["id"] + [
            f"{_quoted_identifier(column)} AS {_quoted_identifier(normalized)}"
            for normalized, column in identity_columns.items()
        ]
        for s in con.execute(f"SELECT {', '.join(select_columns)} FROM sessions"):
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
            row = dict(s)
            cwd = _clean_text(row.get("cwd"))
            repository = _clean_text(row.get("repository"))
            branch = _clean_text(row.get("branch"))
            host_type = _clean_text(row.get("host_type"))
            source, surface = _host_surface(host_type)
            session = {
                "sid": sid,
                "prompt": prompt,
                "turns": turns,
                "last": last,
                "source": source,
                "surface": surface,
            }
            if cwd is not None:
                session["cwd"] = cwd
                session["official_workspace"] = cwd
            elif repository is not None:
                session["official_workspace"] = repository
            if repository is not None:
                session["git_repo_root"] = repository
            if branch is not None:
                session["git_branch"] = branch
            if host_type is not None:
                session["host_type"] = host_type
            out.append(session)
    finally:
        con.close()
    return out


def parse(path: Path):
    if path.suffix == ".db":
        return _parse_sqlite(path)
    if "chatsessions" in {part.casefold() for part in path.parts}:
        return _parse_chat_session(path)
    return _parse_transcript(path)
