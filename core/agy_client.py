"""core/agy_client.py — Provider 'antigravity' via shell-out ao binário `agy`.

Por que existe: a superfície Code Assist (`generateContent`, usada por
core.gemini_cli_client) só serve um subconjunto pobre de modelos
(gemini-2.5-* no pool gemini-cli, gemini-3.1-flash-lite no pool antigravity).
O catálogo rico do Antigravity — gemini-3.5-flash, gemini-3.1-pro,
claude-sonnet-4-6, claude-opus-4-6, gpt-oss-120b-maas — só é acessível pelo
backend NATIVO do antigravity, que o CLI `agy` fala. Este módulo chama o `agy`
em modo headless (`agy -p ... --model ...`) e devolve a resposta.

Isolamento de contexto (crítico): o `agy` é um assistente AGÊNTICO — por padrão
carrega `~/.gemini/GEMINI.md` e `~/.gemini/skills/` (inclui a skill llm-council),
poluindo a saída com vereditos em vez de JSON. Para obter saída determinística,
rodamos o `agy` com um HOME isolado cujo `.gemini` contém apenas as credenciais
(symlinks p/ as reais — refresh do OAuth propaga) e NENHUMA skill/GEMINI.md.

Validado 2026-06-26: claude-sonnet-4-6 e gemini-3.5-flash retornam saída limpa.

Sem dependências novas (subprocess + stdlib).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

# Binário do antigravity CLI. Override via AGY_BIN.
AGY_BIN = os.environ.get("AGY_BIN", str(Path.home() / ".local/bin/agy"))

# Config real do gemini/antigravity (de onde herdamos as credenciais OAuth).
_REAL_GEMINI_DIR = Path(os.environ.get("GEMINI_CLI_DIR", str(Path.home() / ".gemini")))

# HOME isolado p/ o subprocess: .gemini só com auth, sem skills/GEMINI.md.
_ISOLATED_HOME = Path(
    os.environ.get("AGY_ISOLATED_HOME", str(Path.home() / ".cache/hive-mind/agy-isolated"))
)

# Entradas de ~/.gemini que damos ao agy (auth/projeto). Tudo o mais — em especial
# GEMINI.md, skills/, extensions/, history/ — é DELIBERADAMENTE omitido.
_AUTH_ENTRIES = (
    "oauth_creds.json",
    "projects.json",
    "google_accounts.json",
    "installation_id",
    "state.json",
    "config",
)

# Modelos do antigravity acessíveis via `agy` (de `agy models`, IDs do binário).
# Ordem: rápido/barato → capaz. Usada para rotação no 429/erro.
_MODEL_ROTATION = [
    "gemini-3.5-flash",
    "gemini-3.1-pro",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "gpt-oss-120b-maas",
]

DEFAULT_TIMEOUT = int(os.environ.get("AGY_TIMEOUT", "180"))


class AgyCliError(Exception):
    """Erro do provider antigravity/agy (mensagem classificável por call_llm_with_fallback)."""


def _ensure_isolated_home() -> Path:
    """(Re)cria o HOME isolado com symlinks p/ as credenciais reais, sem skills.

    Idempotente e barato: chamado a cada request para refletir rotação de
    credenciais. Symlinks (não cópias) garantem que o refresh do OAuth feito
    pelo agy/gemini grave nos arquivos reais de ~/.gemini.
    """
    gem = _ISOLATED_HOME / ".gemini"
    gem.mkdir(parents=True, exist_ok=True)
    for name in _AUTH_ENTRIES:
        src = _REAL_GEMINI_DIR / name
        link = gem / name
        if not src.exists():
            continue
        # Recria o symlink se ausente ou apontando p/ lugar errado.
        try:
            if link.is_symlink() and Path(os.readlink(link)) == src:
                continue
            if link.exists() or link.is_symlink():
                if link.is_dir() and not link.is_symlink():
                    continue  # diretório real já presente; não mexe
                link.unlink()
            link.symlink_to(src)
        except OSError:
            pass
    return _ISOLATED_HOME


def _extract_json(text: str) -> Optional[str]:
    """Extrai o primeiro objeto JSON balanceado de um texto (tolera prosa/cercas)."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    # Varredura por chaves balanceadas a partir do primeiro '{'.
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        start = text.find("{", start + 1)
    return None


def _run_agy(prompt: str, model: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Roda `agy -p <prompt> --model <model>` com HOME isolado e cwd neutro."""
    if not Path(AGY_BIN).exists():
        raise AgyCliError(f"agy não encontrado em {AGY_BIN} (ajuste AGY_BIN)")

    home = _ensure_isolated_home()
    env = {**os.environ, "HOME": str(home)}
    try:
        proc = subprocess.run(
            [AGY_BIN, "-p", prompt, "--model", model, "--dangerously-skip-permissions"],
            cwd=str(home),  # cwd neutro: evita GEMINI.md/AGENTS.md do projeto
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgyCliError(f"agy timeout ({timeout}s) no modelo {model}") from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:300]
        raise AgyCliError(f"agy exit {proc.returncode} ({model}): {err}")
    return (proc.stdout or "").strip()


def call_agy_text(prompt: str, system_prompt: str = "", model: Optional[str] = None,
                  timeout: int = DEFAULT_TIMEOUT) -> str:
    """Chamada de texto livre via agy. Retorna a resposta crua (stdout)."""
    model = model or _MODEL_ROTATION[0]
    full = f"{system_prompt}\n\n{prompt}".strip() if system_prompt else prompt
    return _run_agy(full, model, timeout)


def call_agy_structured(prompt: str, system_prompt: str, response_model: Any,
                        model: Optional[str] = None,
                        image_path: Optional[str] = None,
                        provider: Optional[str] = None,
                        timeout: int = DEFAULT_TIMEOUT) -> Any:
    """Chama o agy forçando saída JSON e valida com o response_model (Pydantic).

    Ordem de parâmetros idêntica a core.gemini_cli_client.call_gemini_cli_structured
    (prompt, system_prompt, response_model, model, image_path, provider) para ser
    intercambiável no dispatch de core.llm_client.
    """
    if image_path:
        # O modo headless do agy não tem caminho estável p/ imagem; vision usa
        # outros providers. Falha classificável → o fallback do papel assume.
        raise AgyCliError("antigravity (agy) não suporta image_path (use provider de visão)")

    model = model or _MODEL_ROTATION[0]
    schema = response_model.model_json_schema()
    sys_full = (
        f"{system_prompt}\n\n"
        "Responda APENAS com um objeto JSON válido que satisfaça este JSON Schema, "
        "sem markdown, sem cercas de código, sem texto antes ou depois:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )
    raw = _run_agy(f"{sys_full}\n\n{prompt}".strip(), model, timeout)
    payload = _extract_json(raw)
    if payload is None:
        raise AgyCliError(f"agy ({model}) não retornou JSON extraível: {raw[:200]}")
    try:
        return response_model.model_validate_json(payload)
    except Exception as exc:
        raise AgyCliError(f"agy ({model}) JSON inválido p/ schema: {str(exc)[:160]}") from exc
