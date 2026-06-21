#!/usr/bin/env python3
"""Parser para sessões do Codex (CLI e extensão VS Code do OpenAI Codex).

Fonte: ~/.codex/sessions/YYYY/MM/DD/rollout-TIMESTAMP-UUID.jsonl
       ~/.codex/archived_sessions/rollout-TIMESTAMP-UUID.jsonl
Formato: JSONL append-only com events {timestamp, type, payload}.

Tipos relevantes:
  session_meta        → ID da sessão, cwd, source (vscode | cli)
  response_item       → role=user|assistant ou type=function_call|function_call_output
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_VSCODE_REQUEST_RE = re.compile(
    r"## My request for (?:Codex|you):\s*\n(.*?)(?=\n##|\Z)", re.S
)

_META_RE = re.compile(
    r"Chunk ID:.*?\nWall time:.*?\n(?:Process.*?\n)?(?:Original token count:.*?\n)?Output:\n",
    re.DOTALL,
)

# Prefixos de mensagens de sistema do Codex que não devem virar prompt (integralmente)
_SKIP_PREFIXES = (
    "<permissions instructions>",
    "<environment_context>",
    "<turn_aborted>",
    "# AGENTS.md instructions",
    "# Task Group:",
)



def _strip_metadata(output: str) -> str:
    """Remove o cabeçalho de metadados do Codex dos outputs de ferramenta."""
    m = _META_RE.search(output)
    return output[m.end():] if m else output


def _content_text(content) -> str:
    if not content:
        return ""
    if isinstance(content, str):
        return content
    return " ".join(
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("text")
    )


def parse(path: Path):
    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        return []

    sid = cwd = project = None
    first_prompt = last_text = None
    prompts: list[str] = []
    turns: list[dict] = []
    # call_id → {name, args}
    pending: dict[str, dict] = {}

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except Exception:
            continue

        t = d.get("type")
        pl = d.get("payload", {})

        if t == "session_meta":
            sid = pl.get("id")
            cwd = pl.get("cwd") or cwd
            if cwd:
                project = Path(cwd).name

        elif t == "response_item":
            role = pl.get("role")
            item_type = pl.get("type")

            if role in ("user", "assistant"):
                text = _content_text(pl.get("content", []))
                if text and not text.startswith(_SKIP_PREFIXES):
                    if role == "user":
                        # VS Code injeta "# Context from my IDE setup:" antes do pedido real
                        if text.startswith("# Context from my IDE"):
                            m = _VSCODE_REQUEST_RE.search(text)
                            text = m.group(1).strip() if m else ""
                        if text:
                            prompts.append(text[:4000])
                            if first_prompt is None:
                                first_prompt = text[:1000]
                    elif role == "assistant":
                        last_text = text[:500]

            elif item_type == "function_call":
                try:
                    args = json.loads(pl.get("arguments") or "{}")
                except Exception:
                    args = {}
                call_id = pl.get("call_id") or pl.get("id") or ""
                pending[call_id] = {
                    "name": pl.get("name") or "exec_command",
                    "args": args,
                }

            elif item_type == "function_call_output":
                call_id = pl.get("call_id") or ""
                call = pending.pop(call_id, None)
                output = _strip_metadata(pl.get("output") or "")
                if call:
                    turns.append({
                        "tool_name": call["name"],
                        "tool_input": call["args"],
                        "tool_response": output[:3000],
                    })

    if not sid or (not first_prompt and not turns):
        return []

    return [{
        "sid": sid,
        "prompt": first_prompt or "(codex session)",
        "prompts": prompts,
        "turns": turns,
        "last": last_text,
        "project": project,
        "cwd": cwd,
    }]
