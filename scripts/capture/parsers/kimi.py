#!/usr/bin/env python3
"""Parser DEDICADO do Kimi (Kimi Code CLI).

Fonte: ~/.kimi/sessions/<hash>/<uuid>/context.jsonl
Formato: snapshot role-based REESCRITO. Linhas {role, content}; roles internos
         (_system_prompt etc.) são ignorados — só user/assistant viram conteúdo.
         session id = UUID no caminho.

Independente do Hermes — mesma família (role-based) mas fonte/ciclo de vida
distintos, então módulo próprio para poder divergir sem afetar o outro.
"""
from __future__ import annotations

import json
import re
import uuid as _uuid
from pathlib import Path

from capture_core import _text


def parse(path: Path):
    sid = next((p for p in path.parts if re.fullmatch(r"[0-9a-f-]{36}", p)), None) \
        or str(_uuid.uuid5(_uuid.NAMESPACE_URL, str(path)))
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
