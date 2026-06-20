#!/usr/bin/env python3
"""
sanitizer.py — Módulo de sanitização de dados compartilhado.

Remove credenciais, tokens e segredos sensíveis de strings e dicionários
antes de enviá-los ao worker do claude-mem ou qualquer endpoint externo.

Importação:
    from sanitizer import sanitize

Uso direto:
    python3 sanitizer.py "texto com sk-abc123..."
"""
from __future__ import annotations

import re
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Padrões de redação (ordem importa: do mais específico para o mais genérico)
# ---------------------------------------------------------------------------
_PATTERNS: list[tuple[str, str]] = [
    # GitHub tokens
    (r"ghp_[A-Za-z0-9]{36,}", "[REDACTED:github-token]"),
    (r"github_pat_[A-Za-z0-9_]{40,}", "[REDACTED:github-pat]"),
    (r"ghs_[A-Za-z0-9]{36,}", "[REDACTED:github-server-token]"),

    # Anthropic / Claude
    (r"sk-ant-[A-Za-z0-9\-]{20,}", "[REDACTED:anthropic-key]"),

    # OpenAI
    (r"sk-[A-Za-z0-9]{20,}", "[REDACTED:openai-key]"),

    # Google / Gemini / Firebase
    (r"AIzaSy[A-Za-z0-9_\-]{25,}", "[REDACTED:google-key]"),

    # HuggingFace
    (r"hf_[A-Za-z0-9]{30,}", "[REDACTED:huggingface-key]"),

    # AWS
    (r"AKIA[0-9A-Z]{16}", "[REDACTED:aws-access-key]"),
    (r"(?i)aws[_\-\s]?secret[_\-\s]?access[_\-\s]?key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}[\"']?",
     "[REDACTED:aws-secret]"),

    # Postgres / MySQL connection strings
    (r"postgres(?:ql)?://[^@]+@[^\s\"']+", "[REDACTED:db-url]"),
    (r"mysql://[^@]+@[^\s\"']+", "[REDACTED:db-url]"),

    # Generic long hex secrets (32+ chars, isolated)
    (r"\b[0-9a-fA-F]{32,64}\b", "[REDACTED:hex-secret]"),

    # Private key blocks
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
     "[REDACTED:private-key]"),

    # Bearer header values
    (r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*", "[REDACTED:bearer-token]"),
]

# Separate pattern for JSON key-value redaction (requires lambda for group preservation)
_KV_PATTERN = re.compile(
    r'(?i)((?:"|\')(?:bearer|token|api[-_]?key|secret|password|passwd|pwd|access[-_]?token|auth[-_]?token)(?:"|\'))\s*(?:[:,=])\s*(?:"|\')([^"\']{8,})(?:"|\')' ,
    re.IGNORECASE,
)

_COMPILED: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern), replacement)
    for pattern, replacement in _PATTERNS
]


def sanitize(value: Any, _depth: int = 0) -> Any:
    """
    Recursivamente sanitiza strings, dicts e listas removendo segredos.

    Args:
        value: qualquer tipo Python (str, dict, list, int, bool, None)
        _depth: profundidade de recursão (proteção contra loops)

    Returns:
        Valor sanitizado do mesmo tipo original.
    """
    if _depth > 20:
        return value

    if isinstance(value, str):
        return _sanitize_string(value)

    if isinstance(value, dict):
        return {k: sanitize(v, _depth + 1) for k, v in value.items()}

    if isinstance(value, list):
        return [sanitize(item, _depth + 1) for item in value]

    # int, float, bool, None — sem risco, retorna direto
    return value


def _sanitize_string(text: str) -> str:
    """Aplica todos os padrões de redação a uma string."""
    # Key-value JSON pattern (preserva a chave, redige o valor)
    text = _KV_PATTERN.sub(lambda m: f'{m.group(1)}: "[REDACTED:secret]"', text)

    # Demais padrões compilados
    for pattern, replacement in _COMPILED:
        text = pattern.sub(replacement, text)

    return text


# ---------------------------------------------------------------------------
# CLI de teste rápido
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    else:
        raw = sys.stdin.read()

    result = sanitize(raw)
    print(result)
