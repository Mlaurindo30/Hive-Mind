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
from scripts.capture.project_identity import ProjectIdentityResolver


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


def _clean_string(value: Any) -> str | None:
    text = _text(value).strip()
    return text or None


def _known_legacy_project(resolver: ProjectIdentityResolver, value: str | None) -> str | None:
    if value is None:
        return None
    registry = getattr(resolver, "registry", None)
    by_alias = getattr(registry, "by_alias", None)
    return value if callable(by_alias) and by_alias(value) is not None else None


def attach_project_identity(
    provider: str,
    session: dict,
    *,
    resolver: ProjectIdentityResolver,
    default_surface: str | None = None,
) -> dict:
    """Return a normalized session with one canonical identity envelope."""
    normalized = dict(session or {})
    cwd = _clean_string(normalized.get("cwd"))
    surface = (
        _clean_string(normalized.get("surface"))
        or _clean_string(normalized.get("source"))
        or _clean_string(default_surface)
        or "unknown"
    )
    workspace = (
        _clean_string(normalized.get("official_workspace"))
        or _clean_string(normalized.get("workspace_root"))
        or _clean_string(normalized.get("workspace"))
    )
    legacy_project = _clean_string(normalized.get("project"))
    kwargs = {
        "provider": provider,
        "surface": surface,
        "cwd": cwd,
        "explicit_project_id": _clean_string(normalized.get("project_id")),
        "explicit_project_name": _clean_string(normalized.get("project_name")),
        "explicit_project": _known_legacy_project(resolver, legacy_project),
        "official_workspace": workspace,
        "referenced_projects": normalized.get("referenced_projects") or (),
    }
    identity = resolver.resolve(**kwargs)

    envelope = identity.to_dict()
    normalized.update(envelope)
    normalized["project_identity"] = envelope
    normalized["project"] = identity.project_name
    return normalized


def _project_identity_metadata(session: dict) -> dict[str, object] | None:
    envelope = session.get("project_identity")
    if not isinstance(envelope, dict):
        return None
    return {"project_identity": dict(envelope)}


def _merge_event_metadata(
    identity: dict[str, object] | None,
    event_metadata: dict[str, object] | None,
) -> dict[str, object] | None:
    merged = dict(event_metadata or {})
    merged.update(identity or {})
    return merged or None

def session_to_events(provider: str, session: dict) -> list[ProviderEvent]:
    """Map a parser session dict to ordered, deduplicatable ProviderEvents."""
    session = session or {}
    sid = session.get("sid")
    if not provider or not isinstance(sid, str) or not sid.strip():
        return []

    project = _text(session.get("project")).strip() or None
    cwd = _text(session.get("cwd")).strip() or None
    common = {"project": project, "cwd": cwd}
    identity_metadata = _project_identity_metadata(session)
    events: list[ProviderEvent] = []

    for entry in _prompt_entries(session):
        events.append(ProviderEvent.create(
            provider,
            sid,
            EventType.PROMPT,
            entry["content"],
            event_id=entry["event_id"],
            source_position=entry["source_position"],
            metadata=_merge_event_metadata(identity_metadata, entry["metadata"]),
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
        metadata = _merge_event_metadata(identity_metadata, {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_use_id": tool_use_id,
        }) or {}
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
            metadata=identity_metadata,
            **common,
        ))

    return events
