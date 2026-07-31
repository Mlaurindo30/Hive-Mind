#!/usr/bin/env python3
"""Parser dedicado do Antigravity Desktop e CLI.

Desktop grava JSONL reescrito em:
  ~/.gemini/antigravity/brain/<uuid>/.system_generated/logs/transcript_full.jsonl

O Antigravity CLI atual no Windows grava a conversa real em:
  ~/.gemini/antigravity-cli/conversations/<uuid>.db

O banco usa SQLite com payloads Protobuf na tabela ``steps``. USER_INPUT usa
step_type 14 e guarda o texto no campo Protobuf 2; a resposta do modelo usa
step_type 15 e guarda o texto no campo 1. O decoder abaixo lê apenas os campos
length-delimited do nível superior necessários para a captura, sem depender de
uma versão específica das classes Protobuf internas do aplicativo.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

_PAYLOAD_PATH_RE = re.compile(
    r'"(?:Cwd|DirectoryPath|SearchPath|AbsolutePath)"\s*:\s*"([^"]+)"'
)


def _payload_workspace(payload: bytes | None) -> str | None:
    if not isinstance(payload, (bytes, bytearray)):
        return None
    text = bytes(payload).decode("utf-8", errors="ignore")
    candidates = [
        value.replace("\\/", "/")
        for value in _PAYLOAD_PATH_RE.findall(text)
    ]
    for raw in candidates:
        candidate = raw.strip()
        if not candidate:
            continue
        if re.match(r"^[A-Za-z]:/[^/]+$", candidate):
            continue
        path = Path(candidate)
        probe = path if path.suffix == "" else path.parent
        git_dir = probe / ".git"
        if git_dir.is_dir() or git_dir.is_file():
            return str(probe)
    for raw in candidates:
        candidate = raw.strip()
        if not candidate:
            continue
        path = Path(candidate)
        if path.suffix:
            return str(path.parent)
        return str(path)
    return None


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift <= 63:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise ValueError("invalid protobuf varint")


def _protobuf_bytes(data: bytes) -> dict[int, list[bytes]]:
    """Retorna campos length-delimited do nível superior de um Protobuf."""
    fields: dict[int, list[bytes]] = {}
    offset = 0
    while offset < len(data):
        try:
            key, offset = _read_varint(data, offset)
        except ValueError:
            break
        field, wire_type = key >> 3, key & 7
        try:
            if wire_type == 0:
                _, offset = _read_varint(data, offset)
            elif wire_type == 1:
                offset += 8
            elif wire_type == 2:
                size, offset = _read_varint(data, offset)
                end = offset + size
                if end > len(data):
                    break
                fields.setdefault(field, []).append(data[offset:end])
                offset = end
            elif wire_type == 5:
                offset += 4
            else:
                break
        except (ValueError, IndexError):
            break
    return fields


def _text_field(payload: bytes | None, field: int) -> str | None:
    for raw in _protobuf_bytes(bytes(payload or b"")).get(field, []):
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if text:
            return text
    return None


def _step_text(payload: bytes | None, wrapper_field: int, text_field: int) -> str | None:
    envelope = _protobuf_bytes(bytes(payload or b""))
    messages = envelope.get(wrapper_field, [])
    return _text_field(messages[0], text_field) if messages else None

def _storage_identity(path: Path) -> tuple[str, str]:
    parts = {part.lower() for part in path.parts}
    if "antigravity-cli" in parts:
        return "antigravity-cli", "cli"
    if "antigravity-ide" in parts:
        return "antigravity-ide", "ide"
    return "antigravity", "desktop"


def _paired_database(path: Path) -> Path | None:
    sid = next((p for p in path.parts if re.fullmatch(r"[0-9a-f-]{36}", p)), None)
    if not sid:
        return None
    text = str(path).replace("\\", "/")
    if "/.gemini/antigravity-cli/" in text:
        base = path.parents[4]
        return base / "conversations" / f"{sid}.db"
    if "/.gemini/antigravity-ide/" in text:
        base = path.parents[4]
        return base / "conversations" / f"{sid}.db"
    if "/.gemini/antigravity/" in text:
        base = path.parents[4]
        return base / "conversations" / f"{sid}.db"
    return None


def _parse_database(path: Path) -> list[dict]:
    sid = path.stem if re.fullmatch(r"[0-9a-f-]{36}", path.stem) else None
    if not sid:
        return []
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except Exception:
        return []
    prompts: list[str] = []
    prompt_events: list[dict] = []
    turns: list[dict] = []
    last_text = None
    pending_user = None
    workspace = None
    try:
        rows = con.execute(
            "SELECT idx, step_type, step_payload FROM steps ORDER BY idx ASC"
        ).fetchall()
        for idx, step_type, payload in rows:
            if workspace is None:
                workspace = _payload_workspace(payload)
            if step_type == 14:
                text = _step_text(payload, 19, 2)
                if not text:
                    continue
                prompts.append(text)
                pending_user = text
                prompt_events.append({
                    "event_id": str(idx),
                    "content": text,
                    "source_position": f"{path.name}:step:{idx}",
                })
            elif step_type == 15:
                text = _step_text(payload, 20, 1)
                if not text:
                    continue
                last_text = text
                turns.append({
                    "tool_name": "Message",
                    "tool_input": {"prompt": (pending_user or "")[:2000]},
                    "tool_response": text[:4000],
                })
                pending_user = None
    except sqlite3.Error:
        return []
    finally:
        con.close()
    if not prompts and not last_text:
        return []
    source, surface = _storage_identity(path)
    session = {
        "sid": sid,
        "source": source,
        "surface": surface,
        "prompt": prompts[0] if prompts else None,
        "prompts": prompts,
        "prompt_events": prompt_events,
        "turns": turns,
        "last": last_text,
    }
    if workspace is not None:
        session["cwd"] = workspace
        session["official_workspace"] = workspace
    return [session]


def _parse_transcript(path: Path) -> list[dict]:
    paired = _paired_database(path)
    if paired is not None and paired.is_file():
        return []
    sid = next((p for p in path.parts if re.fullmatch(r"[0-9a-f-]{36}", p)), None)
    prompts: list[str] = []
    prompt_events: list[dict] = []
    turns: list[dict] = []
    last_text = None
    for lineno, ln in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        t, idx = d.get("type"), d.get("step_index")
        if t == "USER_INPUT":
            raw = d.get("content") or ""
            match = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.S)
            text = (match.group(1) if match else raw).strip().strip('"')
            if not text:
                continue
            if idx is not None:
                event_id, position = str(idx), f"{path.name}:step:{idx}"
            else:
                event_id, position = None, f"{path.name}:line:{lineno}"
            prompts.append(text)
            prompt_events.append({
                "event_id": event_id,
                "content": text,
                "source_position": position,
            })
        elif t == "PLANNER_RESPONSE" and d.get("tool_calls"):
            for call in d["tool_calls"]:
                args = call.get("args", {}) if isinstance(call, dict) else {}
                turns.append({
                    "tool_name": (call.get("name") if isinstance(call, dict) else None) or "AntigravityTool",
                    "tool_input": args,
                    "tool_response": args.get("toolSummary") or args.get("toolAction") or "ok",
                })
        elif t in ("VIEW_FILE", "LIST_DIRECTORY", "INVOKE_SUBAGENT"):
            content = (d.get("content") or "")[:4000]
            turns.append({
                "tool_name": "".join(word.capitalize() for word in t.split("_")),
                "tool_input": {"step": idx},
                "tool_response": content or "ok",
            })
            if content:
                last_text = content
    if not sid:
        return []
    source, surface = _storage_identity(path)
    return [{
        "sid": sid,
        "source": source,
        "surface": surface,
        "prompt": prompts[0] if prompts else None,
        "prompts": prompts,
        "prompt_events": prompt_events,
        "turns": turns,
        "last": last_text,
    }]


def parse(path: Path):
    return _parse_database(path) if path.suffix.lower() == ".db" else _parse_transcript(path)
