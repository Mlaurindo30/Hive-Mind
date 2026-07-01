#!/usr/bin/env python3
"""Parser DEDICADO do Roo Code (formato Cline).

Fonte: ~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/tasks/<uuid>/ui_messages.json
Formato: ARRAY JSON REESCRITO inteiro. session id = uuid do diretório da task.

Mapeamento say/ask → papel:
  • 1º say:text (a task) e say:user_feedback   → prompt do usuário
  • demais say:text, say:completion_result, ask:followup → resposta do agent
  • api_req_*, error, command_output, checkpoint_saved… → ruído interno, ignora
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from capture_core import project_from_cwd


def _roo_cwd(path: Path) -> str | None:
    """cwd da task = campo `workspace` do history_item.json irmão do ui_messages.json."""
    try:
        hi = path.parent / "history_item.json"
        return json.loads(hi.read_text()).get("workspace") or None
    except Exception:
        return None


def parse(path: Path):
    sid = next((p for p in path.parts if re.fullmatch(r"[0-9a-f-]{36}", p)), path.parent.name)
    cwd = _roo_cwd(path)
    try:
        msgs = json.loads(path.read_text(errors="ignore"))
    except Exception:
        return []
    if not isinstance(msgs, list):
        return []
    prompt, turns, last_text = None, [], None
    pending_user, seen_first_text = None, False

    def add_user(txt):
        nonlocal prompt, pending_user
        txt = (txt or "").strip()
        if not txt:
            return
        prompt = prompt or txt
        pending_user = txt

    def add_assistant(txt):
        nonlocal last_text, pending_user
        txt = (txt or "").strip()
        if not txt:
            return
        last_text = txt
        turns.append({
            "tool_name": "Message",
            "tool_input": {"prompt": (pending_user or "")[:2000]},
            "tool_response": txt[:4000],
        })
        pending_user = None

    for m in msgs:
        if not isinstance(m, dict):
            continue
        typ, txt = m.get("type"), m.get("text") or ""
        if typ == "say":
            sub = m.get("say")
            if sub == "text":
                if not seen_first_text:
                    seen_first_text = True
                    add_user(txt)
                else:
                    add_assistant(txt)
            elif sub == "user_feedback":
                add_user(txt)
            elif sub == "completion_result":
                add_assistant(txt)
        elif typ == "ask" and m.get("ask") == "followup":
            try:
                q = json.loads(txt).get("question") or txt
            except Exception:
                q = txt
            add_assistant(q)
    if not prompt and not turns:
        return []
    return [{"sid": sid, "prompt": prompt, "turns": turns, "last": last_text,
             "project": project_from_cwd(cwd), "cwd": cwd}]
