#!/usr/bin/env python3
"""Non-blocking provider capture hook.

Reads one JSON object from stdin, sanitizes it and appends a normalized
``ProviderEvent`` to the durable ``CaptureQueue`` outbox. The hook NEVER
talks to Claude-Mem, Ollama or the network, and ALWAYS exits zero so that
no provider is ever blocked by capture failures.

Usage (wired by scripts/setup/install-capture-hooks.py):
    python capture-hook.py --provider codex --event-type prompt < payload.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture.capture_events import ProviderEvent  # noqa: E402
from scripts.capture.capture_queue import CaptureQueue  # noqa: E402
from scripts.capture.project_identity import ProjectIdentityResolver  # noqa: E402
from scripts.capture.session_events import attach_project_identity  # noqa: E402
from scripts.utils.sanitizer import sanitize  # noqa: E402

# Reject anything larger than 2 MiB before attempting to parse JSON.
MAX_STDIN_BYTES = 2 * 1024 * 1024

IDENTITY_RESOLVER = ProjectIdentityResolver()

_SESSION_KEYS = ("session_id", "sessionId", "conversation_id", "thread_id")
_PROMPT_KEYS = ("prompt", "user_prompt", "input")
_ASSISTANT_KEYS = ("last_assistant_message", "assistant_message", "message")

_LIFECYCLE_FALLBACK = {
    "session_start": "session started",
    "session_end": "session ended",
}


def default_db_path() -> Path:
    """Resolve the isolated legacy hook outbox path."""
    override = os.environ.get("HIVE_CAPTURE_DB")
    if override:
        return Path(override)
    home = Path(os.environ.get("SINAPSE_HOME", str(ROOT)))
    return home / "logs" / "capture-outbox.db"


def read_stdin_capped(stream=None) -> bytes:
    """Read at most MAX_STDIN_BYTES; raise before any JSON parsing if larger."""
    stream = stream if stream is not None else sys.stdin.buffer
    data = stream.read(MAX_STDIN_BYTES + 1)
    if len(data) > MAX_STDIN_BYTES:
        raise ValueError(f"stdin exceeds {MAX_STDIN_BYTES} bytes")
    return data


def _first_string(payload: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def build_content(event_type: str, payload: dict) -> str:
    """Map Claude/Codex-style and generic hook fields to event content."""
    if event_type in ("prompt", "session_start"):
        text = _first_string(payload, _PROMPT_KEYS)
        if not text:
            text = _LIFECYCLE_FALLBACK.get(event_type, "")
        return text

    if event_type in ("tool_use", "tool_result"):
        parts: dict[str, str] = {}
        tool_name = payload.get("tool_name")
        if tool_name:
            parts["tool_name"] = _as_text(tool_name)
        tool_input = payload.get("tool_input")
        if tool_input is not None:
            parts["tool_input"] = _as_text(tool_input)
        if event_type == "tool_result":
            tool_response = payload.get("tool_response")
            if tool_response is not None:
                parts["tool_response"] = _as_text(tool_response)
        if not parts:
            return ""
        return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))

    text = _first_string(payload, _ASSISTANT_KEYS)
    if not text:
        text = _LIFECYCLE_FALLBACK.get(event_type, "")
    return text


def _first_native_id(payload: dict) -> str | None:
    for key in ("event_id", "eventId", "hook_event_id", "hookEventId", "tool_use_id", "toolUseId", "message_id", "messageId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _occurred_at(payload: dict) -> str | None:
    for key in ("occurred_at", "timestamp", "created_at", "createdAt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
    return None


def _stable_event_id(provider: str, session_id: str, event_type: str, content: str, payload: dict) -> str:
    native = _first_native_id(payload)
    if native:
        return native
    identity = {
        "provider": provider,
        "session_id": session_id,
        "event_type": event_type,
        "content": content,
        "cwd": payload.get("cwd"),
        "project": payload.get("project") or payload.get("project_name"),
        "timestamp": _occurred_at(payload),
    }
    canonical = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _event_metadata(payload: dict) -> dict[str, object] | None:
    metadata: dict[str, object] = {}
    for key in ("tool_name", "tool_input", "tool_response", "tool_use_id"):
        if key in payload and payload[key] is not None:
            metadata[key] = payload[key]
    native = _first_native_id(payload)
    if native:
        metadata["native_event_id"] = native
    return metadata or None


def process(provider: str, event_type: str, raw: bytes) -> dict:
    """Parse, sanitize and enqueue one hook payload. Never raises upward."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return {"ok": False, "error": f"invalid JSON on stdin: {error}"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "stdin JSON must be an object"}

    payload = sanitize(payload)

    session_id = _first_string(payload, _SESSION_KEYS) or "unknown-session"
    content = build_content(event_type, payload)
    if not content.strip():
        return {
            "ok": True,
            "enqueued": False,
            "provider": provider,
            "event_type": event_type,
            "reason": "empty content",
        }

    normalized_session = attach_project_identity(
        provider,
        {**payload, "sid": session_id},
        resolver=IDENTITY_RESOLVER,
        default_surface="hook",
    )
    cwd = normalized_session.get("cwd")
    project = normalized_session["project"]
    event_metadata = _event_metadata(payload) or {}
    event_metadata["project_identity"] = normalized_session["project_identity"]
    timestamp = _occurred_at(payload)
    source_parts = ["hook"]
    if timestamp:
        source_parts.append(timestamp)
    if isinstance(cwd, str) and cwd:
        source_parts.append(cwd)

    event = ProviderEvent.create(
        provider,
        session_id,
        event_type,
        content,
        event_id=_stable_event_id(provider, session_id, event_type, content, payload),
        occurred_at=timestamp,
        source_position=":".join(source_parts),
        project=project if isinstance(project, str) else None,
        cwd=cwd if isinstance(cwd, str) else None,
        metadata=event_metadata,
    )

    queue = CaptureQueue(default_db_path())
    try:
        enqueued = queue.enqueue(event)
    finally:
        queue.close()
    return {
        "ok": True,
        "enqueued": bool(enqueued),
        "provider": provider,
        "event_type": event_type,
        "session_id": session_id,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--event-type", required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_error:
        # --help must keep exiting zero; bad arguments must not block a provider.
        return 0 if exit_error.code == 0 else _emit(
            {"ok": False, "error": "invalid arguments"}
        )

    try:
        raw = read_stdin_capped()
    except (ValueError, OSError) as error:
        return _emit({"ok": False, "error": str(error)})

    try:
        result = process(args.provider, args.event_type, raw)
    except Exception as error:  # noqa: BLE001 — the hook must never fail the provider
        result = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    return _emit(result)


def _emit(result: dict) -> int:
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
