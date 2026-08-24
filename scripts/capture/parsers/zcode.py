#!/usr/bin/env python3
"""Parser para sessões do ZCode CLI.

Fonte: ~/.zcode/cli/rollout/model-io-sess_<uuid>.jsonl (append-only)
       Subagentes gravam model-io-sess_subagent_agent_<uuid>.jsonl no mesmo dir.
Formato: JSONL com registros {"type": "model_io", sessionId, request, response}.

Cada registro é UMA chamada de LLM:
  - request.messages  → conversa acumulada até aquele ponto (o mesmo prompt do
    usuário reaparece em todas as chamadas seguintes; deduplicar por conteúdo)
  - "Primary working directory: ..." (única fonte de cwd — não existe campo
    dedicado como o session_meta do Codex) pode vir em body.system[].text OU
    em uma mensagem injetada pelo runtime dentro de request.messages
  - response.text / response.toolCalls → saída assistente e ferramentas do turno
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid as _uuid
from pathlib import Path

_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
_NOTIFICATION_RE = re.compile(r"<task-notification>.*?</task-notification>", re.DOTALL)
# Âncora em início de linha com bullet opcional (o ZCode já usou tanto
# "Primary working directory: X" quanto "- Primary working directory: X"):
# sem âncora, citações do campo dentro de mensagens do usuário geram falso cwd.
_CWD_RE = re.compile(r"^[ \t]*[-*]?[ \t]*Primary working directory:[ \t]*(.+)$", re.MULTILINE)
# Aceita apenas formas reais de caminho (Windows, UNC, POSIX).
_PATH_SHAPE_RE = re.compile(r"^([A-Za-z]:[\\/]|\\\\|/)")

_PROMPT_LIMIT = 4000
_FIRST_PROMPT_LIMIT = 1000
_LAST_LIMIT = 500
_ZCODE_DB = Path.home() / ".zcode" / "cli" / "db" / "db.sqlite"


def _workspace_from_db(sid: str | None, db_path: Path = _ZCODE_DB) -> str | None:
    """Resolve a sessão no catálogo canônico do ZCode.

    Rollouts de subagente nem sempre repetem ``# Environment``. O banco local do
    próprio ZCode mantém ``session.directory``/``session.path`` e já propaga o
    projeto da sessão pai para cada filho. A consulta é estritamente read-only;
    falha de banco degrada para a extração do JSONL.
    """
    if not sid or not db_path.is_file():
        return None
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1.0) as connection:
            row = connection.execute(
                "SELECT directory, path FROM session WHERE id = ? LIMIT 1",
                (sid,),
            ).fetchone()
    except (OSError, sqlite3.Error):
        return None
    if not row:
        return None
    for value in row:
        candidate = _cwd_value(value)
        if candidate:
            return candidate
    return None


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("text")
        )
    return ""


def _clean_prompt(text: str) -> str:
    """Remove blocos sintéticos injetados pelo runtime antes do pedido real."""
    text = _REMINDER_RE.sub("", text)
    text = _NOTIFICATION_RE.sub("", text)
    text = text.strip()
    if text.startswith(("<system-reminder>", "<task-notification>", "# Environment")):
        # "# Environment" é a injeção de contexto (cwd etc.) que o ZCode manda
        # como mensagem em algumas versões — nunca é pedido do usuário.
        return ""
    return text


def _cwd_value(raw: str) -> str | None:
    """Limpa e valida a captura.

    Env genuíno (parseado do JSON) tem novas linhas REAIS; cópias citadas de
    outro contexto chegam como blob escapado (literal ``\\\\n``, ``\\\\\\\\``) —
    uma linha só. Essas cópias atribuiriam o projeto errado à sessão, então
    são rejeitadas sumariamente antes da validação de formato.
    """
    if "\\n" in raw or "\\\\" in raw:
        return None
    value = raw.split("\r", 1)[0].split("\n", 1)[0].split('"', 1)[0].strip()
    return value if _PATH_SHAPE_RE.match(value) else None


def _cwd_from_record(request: dict) -> str | None:
    """Extrai o cwd do registro, cobrindo todas as localizações observadas.

    O ZCode já colocou o "# Environment" em três lugares conforme a versão:
    body.system[].text, body.messages[N].content (formato wire do Anthropic) e
    request.messages[N].content (lista normalizada).

    Injeções genuínas (texto que COMEÇA com "# Environment") têm prioridade:
    citações do bloco dentro de mensagens do usuário são o mesmo conteúdo, mas
    no meio do texto — confundir os dois atribui o projeto errado à sessão.
    """
    body = request.get("body") or {}
    strong: list[str] = []
    weak: list[str] = []

    def _offer(text: str) -> None:
        if not text:
            return
        (strong if text.lstrip().startswith("# Environment") else weak).append(text)

    system = body.get("system")
    if isinstance(system, list):
        for block in system:
            if isinstance(block, dict):
                _offer(block.get("text", ""))
    elif isinstance(system, str):
        _offer(system)

    for message in body.get("messages") or []:
        if isinstance(message, dict):
            _offer(_text_of(message.get("content")))

    for message in request.get("messages") or []:
        if isinstance(message, dict):
            _offer(_text_of(message.get("content")))

    for text in strong + weak:
        match = _CWD_RE.search(text)
        if match:
            value = _cwd_value(match.group(1))
            if value:
                return value
    return None


def parse(path: Path) -> list[dict]:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        return []

    sid: str | None = None
    cwd: str | None = None
    seen_prompts: set[str] = set()
    prompts: list[str] = []
    prompt_events: list[dict] = []
    turns: list[dict] = []
    last_text: str | None = None

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if record.get("type") != "model_io":
            continue

        sid = sid or record.get("sessionId")
        request = record.get("request") or {}
        response = record.get("response") or {}

        if cwd is None:
            cwd = _cwd_from_record(request)

        request_id = str(record.get("requestId") or "")
        for index, message in enumerate(request.get("messages") or []):
            if message.get("role") != "user":
                continue
            text = _clean_prompt(_text_of(message.get("content")))
            if not text or text in seen_prompts:
                continue
            seen_prompts.add(text)
            prompts.append(text[:_PROMPT_LIMIT])
            prompt_events.append({
                "event_id": request_id or str(len(prompt_events)),
                "content": text[:_PROMPT_LIMIT],
                "source_position": f"{path.name}:model_io:{request_id or index}",
            })

        text = response.get("text")
        if text:
            last_text = text[:_LAST_LIMIT]

        for call in response.get("toolCalls") or []:
            if not isinstance(call, dict):
                continue
            turns.append({
                "tool_name": call.get("name") or "unknown",
                "tool_input": call.get("input") or {},
                "tool_response": "",
            })

    if not prompts and not turns and last_text is None:
        return []
    sid = str(sid or path.stem.replace("model-io-", "") or _uuid.uuid5(_uuid.NAMESPACE_URL, str(path)))
    cwd = _workspace_from_db(sid) or cwd

    return [{
        "sid": str(sid),
        "prompt": prompts[0][:_FIRST_PROMPT_LIMIT] if prompts else None,
        "prompts": prompts,
        "prompt_events": prompt_events,
        "turns": turns,
        "last": last_text,
        "source": "zcode",
        "surface": "cli",
        "official_workspace": cwd,
        "cwd": cwd,
    }]
