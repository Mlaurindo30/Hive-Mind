"""Texto canônico de embedding para neurônios (FASE 1.1, 2026-08-13).

Histórico do bug: três caminhos diferentes embebiam o MESMO neurônio com textos
DIFERENTES:
  - write_indexer.py      → embebia só `body` (sem o label/título)
  - index_neuron_ids      → embebia `content` (sem o label)
  - vector_jobs_worker    → embebia `content` (sem o label)

Resultado: um neurônio indexado por caminhos distintos produzia vetores distintos,
e a busca por similaridade ficava inconsistente. Além disso, NENHUM pré-fixava o
título (`label`), o que reduz a qualidade do embedding (o título é o resumo da
ideia atômica).

Regra canônica (cerebro-writing-spec.md §5):
    embedding_text = f"{label}\\n\\n{body}"

  - `label` (título) SEMPRE pré-fixado — é o sumário da ideia.
  - `body` = conteúdo SEM frontmatter (a coluna `neurons.content` já é corpo puro).
  - `type`/`topic`/`project` NÃO entram no vetor — são metadado filtrável.
  - Truncamento em `max_chars` (default 5000) até o chunking header-based (FASE 4)
    substituir por chunking por heading.

Todos os pontos de embedding DEVEM usar esta função — nunca montar o texto à mão.
"""
from __future__ import annotations

DEFAULT_MAX_CHARS = 5000


def embedding_text(
    label: str | None,
    content: str | None,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Retorna o texto canônico que vira vetor para um neurônio.

    `label` e `content` vêm da tabela `neurons` (content já é corpo puro, sem
    frontmatter). O título é sempre pré-fixado. Se `content` for vazio, o label
    é o próprio texto.
    """
    label_clean = (label or "").strip()
    body = (content or "").strip()

    if not body:
        return label_clean[:max_chars]
    if not label_clean:
        return body[:max_chars]

    # Evita duplicar quando o body já começa com o título.
    if body.lower().startswith(label_clean.lower()):
        return body[:max_chars]

    return f"{label_clean}\n\n{body}"[:max_chars]
