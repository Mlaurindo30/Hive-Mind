"""Normalize parser session dictionaries into ordered ProviderEvent lists.

Parsers keep emitting the legacy session dict ``{sid, prompt, prompts, turns,
last, project?, cwd?, prompt_events?}``. This module preserves that context in
the durable event contract so delivery to Claude-Mem does not lose project,
working directory or tool correlation metadata.
"""
from __future__ import annotations

import json
from typing import Any

from scripts.capture.capture_events import EventType, ProviderEvent


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _prompt_entries(session: dict) -> list[dict]:
    """Uniform prompt view: prefer prompt_events, fall back to prompts/prompt."""
    prompt_events = session.get("prompt_events") or []
    entries: list[dict] = []
    for position_index, event in enumerate(prompt_events):
        if not isinstance(event, dict):
            continue
        content = _text(event.get("content")).strip()
        if not content:
            continue
        raw_metadata = event.get("metadata")
        metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        metadata.update({
            key: value
            for key, value in event.items()
            if key not in {"content", "event_id", "source_position", "metadata"}
        })
        entries.append({
            "content": content,
            "event_id": event.get("event_id") or None,
            "source_position": event.get("source_position") or f"prompt:{position_index}",
            "metadata": metadata or None,
        })
    if entries:
        return entries

    prompts = session.get("prompts") or []
    if not prompts and session.get("prompt"):
        prompts = [session["prompt"]]
    for position_index, prompt in enumerate(prompts):
        content = _text(prompt).strip()
        if not content:
            continue
        entries.append({
            "content": content,
            "event_id": None,
            "source_position": f"prompt:{position_index}",
            "metadata": None,
        })
    return entries


def session_to_events(provider: str, session: dict) -> list[ProviderEvent]:
    """Map a parser session dict to ordered, deduplicatable ProviderEvents."""
    session = session or {}
    sid = session.get("sid")
    if not provider or not isinstance(sid, str) or not sid.strip():
        return []

    project = _text(session.get("project")).strip() or None
    cwd = _text(session.get("cwd")).strip() or None
    common = {"project": project, "cwd": cwd}
    events: list[ProviderEvent] = []

    for entry in _prompt_entries(session):
        events.append(ProviderEvent.create(
            provider,
            sid,
            EventType.PROMPT,
            entry["content"],
            event_id=entry["event_id"],
            source_position=entry["source_position"],
            metadata=entry["metadata"],
            **common,
        ))

    for turn_index, turn in enumerate(session.get("turns") or []):
        if not isinstance(turn, dict):
            continue
        tool_name = _text(turn.get("tool_name")).strip() or "Tool"
        tool_input = turn.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {"value": _text(tool_input)} if tool_input else {}
        tool_use_id = _text(turn.get("tool_use_id")).strip() or (
            f"{provider}:{sid}:turn:{turn_index}"
        )
        metadata = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_use_id": tool_use_id,
        }
        try:
            use_content = json.dumps(
                {"tool_name": tool_name, "tool_input": tool_input},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
        except (TypeError, ValueError):
            use_content = json.dumps({"tool_name": tool_name}, ensure_ascii=False)
        events.append(ProviderEvent.create(
            provider,
            sid,
            EventType.TOOL_USE,
            use_content,
            source_position=f"turn:{turn_index}:tool_use",
            metadata=metadata,
            **common,
        ))
        result_content = _text(turn.get("tool_response")).strip()
        if result_content:
            result_metadata = dict(metadata)
            result_metadata["tool_response"] = result_content
            events.append(ProviderEvent.create(
                provider,
                sid,
                EventType.TOOL_RESULT,
                result_content,
                source_position=f"turn:{turn_index}:tool_result",
                metadata=result_metadata,
                **common,
            ))

    last_text = _text(session.get("last")).strip()
    if last_text:
        events.append(ProviderEvent.create(
            provider,
            sid,
            EventType.ASSISTANT,
            last_text,
            source_position="assistant:last",
            **common,
        ))

    return events
