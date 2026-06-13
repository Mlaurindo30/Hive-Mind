"""
Auto-redaction of PII and secrets from neuron content before federated export.
Redaction is irreversible. Local neurons are never modified.
"""

import copy
import re

# ---------------------------------------------------------------------------
# Compiled patterns — ordered so broader rules don't swallow specific ones.
# CPF/CNPJ come before the generic phone rule; tokens come before email.
# ---------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern, str]] = [
    # 1. API tokens / secrets
    (re.compile(r'sk-[A-Za-z0-9\-_]{20,}'), '[REDACTED:token]'),
    (re.compile(r'GOCSPX-[A-Za-z0-9\-_]+'), '[REDACTED:token]'),
    (re.compile(r'ghp_[A-Za-z0-9]{36}'), '[REDACTED:token]'),
    (re.compile(r'eyJ[A-Za-z0-9\-_=.]+'), '[REDACTED:token]'),
    (re.compile(r'Bearer [A-Za-z0-9\-_.=]+'), '[REDACTED:token]'),
    # 2. Email addresses
    (re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'), '[REDACTED:email]'),
    # 3. IPv4 addresses
    (re.compile(r'\b\d{1,3}(\.\d{1,3}){3}\b'), '[REDACTED:ip]'),
    # 4. IPv6 addresses
    (re.compile(r'([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}'), '[REDACTED:ip]'),
    # 5. Absolute filesystem paths
    (re.compile(r'/home/[^\s]+'), '[REDACTED:path]'),
    (re.compile(r'/root/[^\s]+'), '[REDACTED:path]'),
    (re.compile(r'/Users/[^\s]+'), '[REDACTED:path]'),
    (re.compile(r'/var/[^\s]+'), '[REDACTED:path]'),
    # 6. SSH private key material (handles multiline blocks)
    (re.compile(
        r'-----BEGIN .{0,50}PRIVATE KEY-----.*?-----END .{0,50}PRIVATE KEY-----',
        re.DOTALL,
    ), '[REDACTED:key]'),
    # 8. CPF / CNPJ — applied before phone to avoid digit overlap
    (re.compile(r'\d{3}[.\-]\d{3}[.\-]\d{3}[-]\d{2}'), '[REDACTED:cpf]'),
    (re.compile(r'\d{2}[.\-]\d{3}[.\-]\d{3}\/\d{4}-\d{2}'), '[REDACTED:cpf]'),
    # 7. Phone numbers (broad — runs after CPF/CNPJ)
    (re.compile(r'\+?\d[\d\s\-\(\)]{8,}\d'), '[REDACTED:phone]'),
]


def redact_for_export(text: str) -> str:
    """Apply all redaction rules in sequence. Returns cleaned text.

    The input string is never modified in-place; a new string is returned.
    """
    result = text
    for pattern, replacement in _RULES:
        result = pattern.sub(replacement, result)
    return result


def redact_neuron(neuron: dict) -> dict:
    """Return a deep copy of *neuron* with PII redacted from content and label.

    Only the ``content`` and ``label`` fields are processed. All other fields
    (id, type, visibility, …) pass through unchanged. The original dict is
    never mutated.
    """
    redacted = copy.deepcopy(neuron)
    for field in ('content', 'label'):
        value = redacted.get(field)
        if isinstance(value, str):
            redacted[field] = redact_for_export(value)
    return redacted
