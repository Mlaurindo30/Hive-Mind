#!/usr/bin/env python3
"""Parser dedicado do Kimi CLI legado e do Kimi Code atual.

Fontes:
  ~/.kimi/sessions/<hash>/<uuid>/context.jsonl
  ~/.kimi-code/sessions/<workspace>/session_<uuid>/agents/main/wire.jsonl

O wire atual é append-only. ``turn.prompt`` preserva o texto do usuário;
``context.append_loop_event`` registra conteúdo e pares tool.call/tool.result.
"""
from __future__ import annotations

import json
import re
import uuid as _uuid
from pathlib import Path

from capture_core import project_from_cwd, text_content

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _session_id(path: Path) -> str:
    for part in path.parts:
        match = re.fullmatch(rf"session_({_UUID})", part, re.I)
        if match:
            return match.group(1).lower()
        if re.fullmatch(_UUID, part, re.I):
            return part.lower()
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, str(path)))


def _session_context(path: Path) -> tuple[str | None, str | None]:
    try:
        state = json.loads((path.parents[2] / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, IndexError):
        return None, None
    cwd = state.get("workDir")
    return project_from_cwd(cwd), cwd


def _parse_wire(path: Path) -> list[dict]:
    sid = _session_id(path)
    prompts: list[str] = []
    prompt_events: list[dict] = []
    turns: list[dict] = []
    pending_tools: dict[str, tuple[str, dict]] = {}
    last_text = None

    for lineno, line in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
        try:
            record = json.loads(line)
        except (TypeError, ValueError):
            continue
        record_type = record.get("type")
        if record_type == "turn.prompt":
            text = text_content(record.get("input"))
            if not text:
                continue
            timestamp = record.get("time")
            event_id = str(timestamp) if timestamp is not None else str(lineno)
            prompts.append(text)
            prompt_events.append({
                "event_id": event_id,
                "content": text,
                "source_position": (
                    f"{path.name}:time:{timestamp}" if timestamp is not None
                    else f"{path.name}:line:{lineno}"
                ),
            })
            continue
        if record_type == "context.append_message":
            message = record.get("message") or {}
            if message.get("role") == "assistant":
                last_text = text_content(message.get("content")) or last_text
            continue
        if record_type != "context.append_loop_event":
            continue
        event = record.get("event") or {}
        event_type = event.get("type")
        if event_type == "content.part":
            part = event.get("part") or {}
            if part.get("type") == "text" and part.get("text"):
                last_text = str(part["text"])
        elif event_type == "tool.call":
            call_id = str(event.get("toolCallId") or event.get("uuid") or lineno)
            pending_tools[call_id] = (
                str(event.get("name") or "KimiTool"),
                event.get("args") if isinstance(event.get("args"), dict) else {},
            )
        elif event_type == "tool.result":
            call_id = str(event.get("toolCallId") or event.get("parentUuid") or "")
            name, args = pending_tools.pop(call_id, ("KimiTool", {}))
            result = event.get("result") or {}
            output = result.get("output") if isinstance(result, dict) else result
            turns.append({
                "tool_name": name,
                "tool_input": args,
                "tool_response": text_content(output) or "ok",
            })

    project, cwd = _session_context(path)
    if not prompts and not turns and not last_text:
        return []
    return [{
        "sid": sid,
        "prompt": prompts[0] if prompts else None,
        "prompts": prompts,
        "prompt_events": prompt_events,
        "turns": turns,
        "last": last_text,
        "project": project,
        "cwd": cwd,
    }]


def _parse_legacy(path: Path) -> list[dict]:
    sid = _session_id(path)
    prompt, turns, last_text, pending_user = None, [], None, None
    for line in path.read_text(errors="ignore").splitlines():
        try:
            record = json.loads(line)
        except (TypeError, ValueError):
            continue
        role = record.get("role")
        if role == "user":
            text = text_content(record.get("content"))
            prompt = prompt or text
            pending_user = text
        elif role == "assistant":
            text = text_content(record.get("content"))
            last_text = text or last_text
            turns.append({
                "tool_name": "Message",
                "tool_input": {"prompt": (pending_user or "")[:2000]},
                "tool_response": (text or "ok")[:4000],
            })
            pending_user = None
    return [{"sid": sid, "prompt": prompt, "turns": turns, "last": last_text}]


def parse(path: Path):
    return _parse_wire(path) if path.name == "wire.jsonl" else _parse_legacy(path)