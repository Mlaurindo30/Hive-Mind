#!/usr/bin/env python3
"""
Hook Stop — consolida session log ativo via LLM (papel session_summarizer).

Localiza o session log ativo (mais recente arquivo em sessoes/YYYY/MM/DD/),
lê o conteúdo, gera `SessionSummary` via LLM com fallback automático, e
injeta o resultado em `## Resumo` (substituindo placeholder). Marca o
frontmatter com `consolidated: true` para que session_update.py saiba parar
de fazer append.

Em caso de falha de LLM (auth/quota/transient esgotado): marca `consolidated:
true` mesmo assim com `[Resumo não gerado — erro: <motivo>]` em `## Resumo`
para que a sessão não fique em loop infinito no próximo Stop.

Exit 0 sempre (Stop hook não deve bloquear o shutdown do Claude Code).
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(_HERE.parent))
sys.path.append(SINAPSE_HOME)

# Carrega .env cedo (antes de qualquer leitura de role_config)
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(SINAPSE_HOME) / ".env")
except ImportError:
    pass

from core import paths as cp  # noqa: E402
from core.auth import get_role_config, load_env  # noqa: E402
from core.llm_client import call_llm_with_fallback, classify_llm_error  # noqa: E402
from core.schemas.session_models import SessionSummary  # noqa: E402

load_env()

# Override para testes: redireciona SESSIONS_ROOT para tmp_path
_TEST_SESSIONS_ROOT = os.environ.get("SESSIONS_ROOT_OVERRIDE")
SESSIONS_ROOT = Path(_TEST_SESSIONS_ROOT) if _TEST_SESSIONS_ROOT else cp.SESSIONS_ROOT

# Resolve provider/model do papel session_summarizer (herda do dreamer se vazio)
_cfg = get_role_config("session_summarizer") or {}
LLM_PROVIDER = _cfg.get("provider")
LLM_MODEL = _cfg.get("model")

CONSOLIDATOR_PROMPT = """Você é o consolidator de sessões do Hive-Mind (cérebro digital do Michel).
Dado o transcript bruto de uma sessão de trabalho (tool calls, decisões, comandos),
produza um resumo estruturado com 3-7 bullets do que rolou, decisões explícitas
tomadas, e perguntas em aberto que ficaram sem resposta.

Foco no que foi FEITO/DECIDIDO/ENCONTRADO, não em processo. Verbos no passado.
Responda APENAS com JSON que casa SessionSummary (bullets, decisions, open_questions).

Se o transcript estiver vazio ou sem substância, retorne arrays vazios."""


def _read_hook_payload() -> dict:
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                return json.loads(raw)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _find_active_session(when: datetime) -> Path | None:
    folder = SESSIONS_ROOT / when.strftime("%Y/%m/%d")
    if not folder.exists():
        return None
    candidates = sorted(
        folder.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _is_already_consolidated(target: Path) -> bool:
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(re.search(r"^consolidated:\s*true", text, re.MULTILINE | re.IGNORECASE))


def _extract_transcript(target: Path, max_chars: int = 12000) -> str:
    """Extrai o transcript bruto do session log, truncando para caber no contexto."""
    text = target.read_text(encoding="utf-8")
    # Remove frontmatter para enviar só o conteúdo
    text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... truncado em {max_chars} chars ...]"
    return text


def _render_summary(summary: SessionSummary) -> str:
    parts = ["### Bullets"]
    for b in summary.bullets:
        parts.append(f"- {b}")
    if summary.decisions:
        parts.append("\n### Decisões")
        for d in summary.decisions:
            parts.append(f"- {d}")
    if summary.open_questions:
        parts.append("\n### Perguntas em aberto")
        for q in summary.open_questions:
            parts.append(f"- {q}")
    return "\n".join(parts)


def _inject_summary(target: Path, summary_text: str, ok: bool, error_msg: str = "") -> None:
    """Substitui a seção ## Resumo pelo conteúdo gerado, marca consolidated: true."""
    text = target.read_text(encoding="utf-8")

    if not ok:
        # Falha: marca erro no resumo, mas fecha a sessão para não loopar
        summary_text = f"⚠️ Resumo não gerado — erro: {error_msg}\n"

    # Substitui a seção ## Resumo inteira (até próxima seção ## ou EOF)
    new_section = f"## Resumo\n\n{summary_text}\n"
    if re.search(r"^## Resumo\s*$", text, re.MULTILINE):
        text = re.sub(
            r"## Resumo\s*\n.*?(?=^## |\Z)",
            new_section,
            text,
            count=1,
            flags=re.MULTILINE | re.DOTALL,
        )
    else:
        # Sem seção ## Resumo — insere antes de ## Related se existir
        if "## Related" in text:
            text = text.replace("## Related", new_section + "\n## Related", 1)
        else:
            text += f"\n{new_section}"

    # Marca consolidated: true no frontmatter
    if re.search(r"^consolidated:", text, re.MULTILINE):
        text = re.sub(r"^consolidated:.*$", "consolidated: true", text, count=1, flags=re.MULTILINE)
    else:
        text = re.sub(
            r"^(---\n)",
            r"\1consolidated: true\n",
            text,
            count=1,
            flags=re.MULTILINE,
        )

    # Atualiza timestamp updated:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = re.sub(r"^updated:.*$", f"updated: {now}", text, count=1, flags=re.MULTILINE)

    target.write_text(text, encoding="utf-8")


def main() -> int:
    dry_run = os.environ.get("DRY_RUN", "0") == "1"
    _ = _read_hook_payload()
    now = datetime.now()

    target = _find_active_session(now)
    if target is None:
        return 0  # nada a consolidar

    if _is_already_consolidated(target):
        return 0  # já consolidado em Stop anterior

    transcript = _extract_transcript(target)
    if not transcript.strip():
        _inject_summary(target, "_Sessão vazia (placeholder criado mas sem ações registradas)._",
                       ok=True)
        return 0

    if dry_run:
        print(f"[session_consolidator] DRY_RUN: consolidaria {target.relative_to(SINAPSE_HOME)}", file=sys.stderr)
        return 0

    if not LLM_PROVIDER or not LLM_MODEL:
        _inject_summary(target, "", ok=False, error_msg="role session_summarizer não configurado")
        return 0

    # Chama LLM
    try:
        prompt = f"TRANSCRIPT DA SESSÃO:\n```\n{transcript}\n```\n\nGere o JSON do SessionSummary."
        summary = call_llm_with_fallback(
            "session_summarizer",
            prompt,
            CONSOLIDATOR_PROMPT,
            SessionSummary,
        )
        rendered = _render_summary(summary)
        _inject_summary(target, rendered, ok=True)
        print(f"[session_consolidator] ✓ {target.relative_to(SINAPSE_HOME)}", file=sys.stderr)
    except Exception as e:
        kind = classify_llm_error(e)
        _inject_summary(target, "", ok=False, error_msg=f"{kind}: {e}")
        print(f"[session_consolidator] ✗ {kind}: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
