#!/usr/bin/env python3
"""Parser for current Qwen Code CLI and Desktop JSONL conversations.

Both surfaces persist conversations under:
  ~/.qwen/projects/<project>/chats/<session-id>.jsonl
"""
from __future__ import annotations

import json
import uuid as _uuid
from pathlib import Path

from capture_core import text_content


def _message_text(record: dict) -> str | None:
    message = record.get("message") or {}
    return text_content(message.get("parts") or message.get("content"))


def parse(path: Path) -> list[dict]:
    prompts: list[str] = []
    prompt_events: list[dict] = []
    turns: list[dict] = []
    pending_user: str | None = None
    last_text: str | None = None
    sid: str | None = None
    cwd: str | None = None
    source: str | None = None
    surface: str | None = None

    for lineno, line in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
        try:
            record = json.loads(line)
        except (TypeError, ValueError):
            continue
        sid = sid or record.get("sessionId")
        cwd = cwd or record.get("cwd")
        source = source or record.get("source") or record.get("client")
        surface = surface or record.get("surface")
        record_type = record.get("type")
        text = _message_text(record)
        if record_type == "user" and text:
            event_id = str(record.get("uuid") or lineno)
            prompts.append(text)
            prompt_events.append({
                "event_id": event_id,
                "content": text,
                "source_position": f"{path.name}:uuid:{event_id}",
            })
            pending_user = text
        elif record_type == "assistant" and text:
            last_text = text
            turns.append({
                "tool_name": "Message",
                "tool_input": {"prompt": (pending_user or "")[:2000]},
                "tool_response": text[:4000],
            })
            pending_user = None

    if not prompts and not turns and not last_text:
        return []
    session_id = str(sid or path.stem or _uuid.uuid5(_uuid.NAMESPACE_URL, str(path)))
    return [{
        "sid": session_id,
        "prompt": prompts[0] if prompts else None,
        "prompts": prompts,
        "prompt_events": prompt_events,
        "turns": turns,
        "last": last_text,
        "source": source or "qwen",
        "surface": surface or "unknown",
        "official_workspace": cwd,
        "cwd": cwd,
    }]
