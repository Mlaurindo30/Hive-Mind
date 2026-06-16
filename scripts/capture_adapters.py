#!/usr/bin/env python3
"""
capture_adapters.py — Registro ÚNICO e declarativo das ferramentas capturadas.

Cada ferramenta = uma entrada AUTOCONTIDA: seu parser DEDICADO (parsers/<tool>.py),
suas fontes/dirs e seu dono/modo. Não há sobreposição de parser nem de config
entre ferramentas — mimo≠kilo, antigravity≠gemini, hermes≠kimi, etc.

  owner : "realtime" (daemon inotify, ao vivo) | "timer" (tailer periódico)
  mode  : "tail"    → arquivo APPEND-ONLY
          "reparse" → arquivo REESCRITO / array JSON / SQLite
          (informativo: o daemon trata todos via reparse+content-hash de forma
           uniforme; o rótulo documenta a natureza da fonte)
  parser: callable DEDICADO da ferramenta (parsers.<tool>.parse)
  watch : dirs p/ inotify (realtime)   |   sources : globs dos arquivos a parsear
"""
from __future__ import annotations

from pathlib import Path

from parsers import (
    antigravity as _antigravity,
    copilot as _copilot,
    hermes as _hermes,
    kilo as _kilo,
    kimi as _kimi,
    mimo as _mimo,
    openclaw as _openclaw,
    roo as _roo,
)

HOME = Path.home()

ADAPTERS = {
    # ── append-only ──────────────────────────────────────────────────────────
    "copilot": {
        "owner": "realtime", "mode": "tail", "parser": _copilot.parse,
        "watch": [str(HOME / ".config/Code/User/workspaceStorage/*/GitHub.copilot-chat/transcripts")],
        "sources": [str(HOME / ".config/Code/User/workspaceStorage/*/GitHub.copilot-chat/transcripts/*.jsonl")],
    },
    "hermes": {
        "owner": "realtime", "mode": "tail", "parser": _hermes.parse,
        "watch": [str(HOME / ".hermes/sessions")],
        "sources": [str(HOME / ".hermes/sessions/*.jsonl")],
    },
    # ── reescrito / array / sqlite ───────────────────────────────────────────
    "antigravity": {
        "owner": "realtime", "mode": "reparse", "parser": _antigravity.parse,
        "watch": [str(HOME / ".gemini/antigravity-cli/brain/*/.system_generated/logs")],
        "sources": [str(HOME / ".gemini/antigravity-cli/brain/*/.system_generated/logs/transcript_full.jsonl")],
    },
    "kimi": {
        "owner": "realtime", "mode": "reparse", "parser": _kimi.parse,
        "watch": [str(HOME / ".kimi/sessions/*/*")],
        "sources": [str(HOME / ".kimi/sessions/*/*/context.jsonl")],
    },
    "kilo": {
        "owner": "realtime", "mode": "reparse", "parser": _kilo.parse,
        "watch": [str(HOME / "snap/code/*/.local/share/kilo")],
        "sources": [str(HOME / "snap/code/*/.local/share/kilo/kilo.db")],
    },
    "roo": {
        "owner": "realtime", "mode": "reparse", "parser": _roo.parse,
        "watch": [
            str(HOME / ".config/Code/User/globalStorage/rooveterinaryinc.roo-cline/tasks"),
            str(HOME / ".config/Code/User/globalStorage/rooveterinaryinc.roo-cline/tasks/*"),
        ],
        "sources": [str(HOME / ".config/Code/User/globalStorage/rooveterinaryinc.roo-cline/tasks/*/ui_messages.json")],
    },
    # ── também em realtime (envio imediato via inotify) ──────────────────────
    # mimo é CLI, mas grava num dir vigiável → captura na hora como os demais.
    "mimo": {
        "owner": "realtime", "mode": "reparse", "parser": _mimo.parse,
        "watch": [str(HOME / ".local/share/mimocode")],
        "sources": [str(HOME / ".local/share/mimocode/mimocode.db")],
    },
    "openclaw": {
        "owner": "realtime", "mode": "reparse", "parser": _openclaw.parse,
        "watch": [str(HOME / ".openclaw/tasks")],
        "sources": [str(HOME / ".openclaw/tasks/runs.sqlite")],
    },
    # gemini-cli NÃO está aqui: o claude-mem já o captura NATIVAMENTE (conexão
    # direta, envio imediato) — capturá-lo aqui de novo só duplicaria.
}


def adapters_by_owner(owner: str) -> dict:
    return {k: v for k, v in ADAPTERS.items() if v["owner"] == owner}
