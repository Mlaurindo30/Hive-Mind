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

import os
from pathlib import Path

from parsers import (
    antigravity as _antigravity,
    codex as _codex,
    copilot as _copilot,
    hermes as _hermes,
    kilo as _kilo,
    kimi as _kimi,
    qwen as _qwen,
    mimo as _mimo,
    openclaw as _openclaw,
    roo as _roo,
    swarmclaw as _swarmclaw,
    zcode as _zcode,
)


def _parse_screenpipe(_source=None) -> list[dict]:
    """Adapter Screenpipe — lê OCR e áudio via REST (sem arquivo local).

    Retorna lista vazia se Screenpipe não estiver rodando (safe no-op).
    """
    try:
        from parsers.screenpipe import screenpipe_alive, fetch_recent_ocr, fetch_recent_audio
        if not screenpipe_alive():
            return []
        return fetch_recent_ocr(since_minutes=60) + fetch_recent_audio(since_minutes=60)
    except Exception:
        return []

HOME = Path.home()


def _vscode_user_dir() -> Path:
    """Diretório User do VS Code por plataforma.

    Windows: %APPDATA%\\Code\\User (fallback ~\\AppData\\Roaming\\Code\\User).
    POSIX:   ~/.config/Code/User (comportamento original).
    """
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else HOME / "AppData" / "Roaming"
        return base / "Code" / "User"
    return HOME / ".config" / "Code" / "User"


VSCODE_USER = _vscode_user_dir()


def _local_appdata_dir() -> Path:
    if os.name == "nt":
        value = os.environ.get("LOCALAPPDATA")
        return Path(value) if value else HOME / "AppData" / "Local"
    return HOME / ".local" / "share"


def _hermes_paths() -> tuple[list[str], list[str]]:
    if os.name == "nt":
        base = _local_appdata_dir() / "hermes"
        return [str(base)], [str(base / "state.db")]
    base = HOME / ".hermes"
    return [str(base)], [str(base / "state.db")]


def _kilo_paths() -> tuple[list[str], list[str]]:
    if os.name == "nt":
        canonical_cli = HOME / ".local" / "share" / "kilo"
        roots = [
            canonical_cli,
            VSCODE_USER / "globalStorage" / "kilocode.kilo-code",
            HOME / ".kilocode",
            HOME / ".kilo",
        ]
        watches = [str(root) for root in roots]
        sources = [str(canonical_cli / "kilo.db")]
        sources.extend(str(root / "**" / "kilo.db") for root in roots[1:])
        return watches, sources
    base = HOME / "snap" / "code" / "*" / ".local" / "share" / "kilo"
    return [str(base)], [str(base / "kilo.db")]


HERMES_WATCH, HERMES_SOURCES = _hermes_paths()
KILO_WATCH, KILO_SOURCES = _kilo_paths()

ADAPTERS = {
    # ── append-only ──────────────────────────────────────────────────────────
    # Codex CLI e extensão VS Code do OpenAI Codex gravam cada sessão em
    # ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl (append-only). Sessões
    # encerradas vão para ~/.codex/archived_sessions/. O capturador via hooks
    # (~/.codex/hooks.json) envia em tempo real; este adapter é o fallback
    # por arquivo, idêntico em estrutura ao antigravity/kimi.
    "codex": {
        "owner": "realtime", "mode": "tail", "parser": _codex.parse,
        "watch": [
            str(HOME / ".codex/sessions/*/*/*"),
            str(HOME / ".codex/archived_sessions"),
        ],
        "sources": [
            str(HOME / ".codex/sessions/*/*/*/rollout-*.jsonl"),
            str(HOME / ".codex/archived_sessions/rollout-*.jsonl"),
        ],
    },
    "copilot": {
        "owner": "realtime", "mode": "reparse", "parser": _copilot.parse,
        "watch": [
            str(HOME / ".copilot"),
            str(VSCODE_USER / "globalStorage/github.copilot-chat"),
            str(VSCODE_USER / "workspaceStorage/*/GitHub.copilot-chat/transcripts"),
            str(VSCODE_USER / "workspaceStorage/*/chatSessions"),
        ],
        "sources": [
            str(HOME / ".copilot/session-store.db"),
            str(VSCODE_USER / "globalStorage/github.copilot-chat/session-store.db"),
            str(VSCODE_USER / "workspaceStorage/*/GitHub.copilot-chat/transcripts/*.jsonl"),
            str(VSCODE_USER / "workspaceStorage/*/chatSessions/*.jsonl"),
        ],
    },
    "hermes": {
        "owner": "realtime", "mode": "reparse", "parser": _hermes.parse,
        "watch": HERMES_WATCH,
        "sources": HERMES_SOURCES,
    },
    # ── reescrito / array / sqlite ───────────────────────────────────────────
    # Antigravity tem DOIS layouts com o mesmo esquema de transcript:
    #   Desktop (IDE):  ~/.gemini/antigravity/brain/<uuid>/...
    #   CLI:            ~/.gemini/antigravity-cli/brain/<uuid>/...
    "antigravity": {
        "owner": "realtime", "mode": "reparse", "parser": _antigravity.parse,
        "watch": [
            str(HOME / ".gemini/antigravity/brain"),                                 # sentinela: detecta novos UUIDs (Desktop)
            str(HOME / ".gemini/antigravity/conversations"),
            str(HOME / ".gemini/antigravity-ide/brain"),                         # storage real do IDE Windows
            str(HOME / ".gemini/antigravity-ide/conversations"),                 # SQLite real do IDE Windows
            str(HOME / ".gemini/antigravity/brain/*/.system_generated/logs"),        # filtrado por mtime em refresh()
            str(HOME / ".gemini/antigravity-cli/brain"),                             # sentinela: detecta novos UUIDs (CLI)
            str(HOME / ".gemini/antigravity-cli/conversations"),                 # SQLite real do CLI Windows
            str(HOME / ".gemini/antigravity-cli/brain/*/.system_generated/logs"),    # filtrado por mtime em refresh()
        ],
        "sources": [
            str(HOME / ".gemini/antigravity/brain/*/.system_generated/logs/transcript_full.jsonl"),
            str(HOME / ".gemini/antigravity/conversations/*.db"),
            str(HOME / ".gemini/antigravity-ide/brain/*/.system_generated/logs/transcript_full.jsonl"),
            str(HOME / ".gemini/antigravity-ide/conversations/*.db"),
            str(HOME / ".gemini/antigravity-cli/brain/*/.system_generated/logs/transcript_full.jsonl"),
            str(HOME / ".gemini/antigravity-cli/conversations/*.db"),
        ],
    },
    "kimi": {
        "owner": "realtime", "mode": "reparse", "parser": _kimi.parse,
        "watch": [
            str(HOME / ".kimi/sessions"),
            str(HOME / ".kimi/sessions/*/*"),
            str(HOME / ".kimi-code/sessions"),
        ],
        "sources": [
            str(HOME / ".kimi/sessions/*/*/context.jsonl"),
            str(HOME / ".kimi-code/sessions/**/agents/main/wire.jsonl"),
        ],
    },
    "qwen": {
        "owner": "realtime", "mode": "tail", "parser": _qwen.parse,
        "watch": [str(HOME / ".qwen/projects")],
        "sources": [str(HOME / ".qwen/projects/**/chats/*.jsonl")],
    },    "kilo": {
        "owner": "realtime", "mode": "reparse", "parser": _kilo.parse,
        "watch": KILO_WATCH,
        "sources": KILO_SOURCES,
    },
    "roo": {
        "owner": "realtime", "mode": "reparse", "parser": _roo.parse,
        "watch": [
            str(VSCODE_USER / "globalStorage/rooveterinaryinc.roo-cline/tasks"),
            str(VSCODE_USER / "globalStorage/rooveterinaryinc.roo-cline/tasks/*"),
        ],
        "sources": [str(VSCODE_USER / "globalStorage/rooveterinaryinc.roo-cline/tasks/*/ui_messages.json")],
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
    # SwarmClaw armazena sessões e runs em SQLite. O parser preserva o CWD
    # bruto; a identidade canônica é resolvida depois por attach_project_identity.
    "swarmclaw": {
        "owner": "realtime", "mode": "reparse", "parser": _swarmclaw.parse,
        "watch": [str(HOME / ".swarmclaw/data")],
        "sources": [str(HOME / ".swarmclaw/data/swarmclaw.db")],
    },
    # ZCode CLI: cada sessão é um JSONL append-only em ~/.zcode/cli/rollout
    # (model-io-sess_*.jsonl, incl. subagentes). O parser deduplica prompts que
    # reaparecem a cada chamada e extrai o cwd do bloco system.
    "zcode": {
        "owner": "realtime", "mode": "tail", "parser": _zcode.parse,
        "watch": [str(HOME / ".zcode/cli/rollout")],
        "sources": [str(HOME / ".zcode/cli/rollout/model-io-sess_*.jsonl")],
    },
    # antigravity-cli NÃO está aqui: o claude-mem já o captura NATIVAMENTE via
    # hooks (adapter antigravity-cli em src/cli/adapters, desde v13.10.0 quando a
    # Google deprecou o Gemini CLI). Capturá-lo aqui de novo só duplicaria.
    # Nota (2026-08-12): o claude-mem REMOVEU o gemini-cli nativo — não existe
    # mais captura nativa de gemini; quem migrar do Gemini usa o Antigravity CLI.

    # Screenpipe: daemon Rust que captura tela+áudio continuamente (OCR + Whisper).
    # owner=timer: tailer periódico consulta REST /search a cada ciclo.
    # sources=[] / watch=[]: sem arquivo local — fonte é a API REST.
    # Ativa automaticamente quando screenpipe_alive() == True.
    "screenpipe": {
        "owner": "timer",
        "mode": "reparse",
        "parser": _parse_screenpipe,
        "sources": [],
        "watch": [],
    },
}


def adapters_by_owner(owner: str) -> dict:
    return {k: v for k, v in ADAPTERS.items() if v["owner"] == owner}
