#!/usr/bin/env python3
"""Parser DEDICADO do Hermes.

Fonte: ~/.hermes/sessions/*.jsonl
Formato: JSONL role-based APPEND-ONLY — linhas {role: user|assistant|..., content}.
         session id = UUID estável derivado do caminho do arquivo.
"""
from __future__ import annotations

import json
import uuid as _uuid
from pathlib import Path

from capture_core import _text


def parse(path: Path):
    sid = str(_uuid.uuid5(_uuid.NAMESPACE_URL, str(path)))
    prompt, turns, last_text, pending_user = None, [], None, None
    for ln in path.read_text(errors="ignore").splitlines():
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        role = d.get("role")
        if role == "user":
            txt = _text(d.get("content"))
            prompt = prompt or txt
            pending_user = txt
        elif role == "assistant":
            txt = _text(d.get("content"))
            last_text = txt or last_text
            turns.append({
                "tool_name": "Message",
                "tool_input": {"prompt": (pending_user or "")[:2000]},
                "tool_response": (txt or "ok")[:4000],
            })
            pending_user = None
    return [{"sid": sid, "prompt": prompt, "turns": turns, "last": last_text}]
