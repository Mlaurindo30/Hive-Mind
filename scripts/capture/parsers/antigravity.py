#!/usr/bin/env python3
"""Parser DEDICADO do Antigravity (Desktop e CLI Gemini "antigravity").

Fontes: ~/.gemini/antigravity/brain/<uuid>/.system_generated/logs/transcript_full.jsonl (Desktop)
        ~/.gemini/antigravity-cli/brain/<uuid>/.system_generated/logs/transcript_full.jsonl (CLI)
Formato: JSONL "full dump" REESCRITO inteiro a cada passo (não é append-only).
Eventos: USER_INPUT (pedido), PLANNER_RESPONSE (tool_calls), VIEW_FILE /
         LIST_DIRECTORY / INVOKE_SUBAGENT (ações).

Cada USER_INPUT é preservado (não apenas o último). `prompt_events` expõe o
step_index nativo como event_id e uma posição de origem estável — como o
arquivo é reescrito a cada passo, a posição usa o step_index (não offsets).

Independente do gemini-cli (que grava em ~/.gemini/tmp/.../chats e tem outro
esquema de eventos) — cada um tem seu próprio módulo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def parse(path: Path):
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
            m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.S)
            text = (m.group(1) if m else raw).strip().strip('"')
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
            for j, c in enumerate(d["tool_calls"]):
                a = c.get("args", {}) if isinstance(c, dict) else {}
                turns.append({
                    "tool_name": (c.get("name") if isinstance(c, dict) else None) or "AntigravityTool",
                    "tool_input": a,
                    "tool_response": a.get("toolSummary") or a.get("toolAction") or "ok",
                })
        elif t in ("VIEW_FILE", "LIST_DIRECTORY", "INVOKE_SUBAGENT"):
            content = (d.get("content") or "")[:4000]
            turns.append({
                "tool_name": "".join(w.capitalize() for w in t.split("_")),
                "tool_input": {"step": idx},
                "tool_response": content or "ok",
            })
            if content:
                last_text = content
    if not sid:
        return []
    return [{
        "sid": sid,
        "prompt": prompts[0] if prompts else None,
        "prompts": prompts,
        "prompt_events": prompt_events,
        "turns": turns,
        "last": last_text,
    }]
