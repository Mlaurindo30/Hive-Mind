"""Typed memory decay (adotado do OmniRoute TV6, 2026-08-12).

Conhecimento durável é imune à penalidade de staleness; conhecimento efêmero
decaí. A imunidade vem de duas fontes independentes, espelhando o modelo do
OmniRoute (typedDecay.ts):

  - **Type immunity** — um tipo classificado como durável nunca decai por TTL.
    Por padrão `fact`, `decision`, `learning`, `preference`, `rationale`,
    `code_symbol` e `document_chunk` são duráveis (conhecimento que não perde
    validade com o tempo). Tipos efêmeros (`operational_fact`, `project_status`,
    `visual_observation`, `next_step`) decaem — são estado transitório, não
    conhecimento.

  - **Access immunity** — um item injetado no prompt >= N vezes
    (`HIVE_STALENESS_ACCESS_IMMUNITY`, default 3) ganhou o sustento e nunca é
    demovido por staleness, independentemente do tipo.

Isto ataca diretamente o ruído observado na promoção direta (K3): observações
operacionais de sessão ("o PID é 90772", "a taxa de vetorização é 5.2%") eram
promovidas como `fact` permanente. Com typed decay, `operational_fact` e
`project_status` decaem em vez de poluir o vault para sempre.

Nenhuma função aqui deleta nada: a penalidade é de ranking (score * factor),
nunca exclusão — mesmo contrato do `_apply_governance_penalty` existente.
"""
from __future__ import annotations

import os
from typing import Any


# Tipos de conhecimento duráveis (imunes à penalidade de staleness por tipo).
DURABLE_TYPES: frozenset[str] = frozenset(
    {
        "fact",
        "decision",
        "learning",
        "preference",
        "rationale",
        "code_symbol",
        "document_chunk",
    }
)

# Tipos efêmeros (decaem com o tempo) — estado transitório, não conhecimento.
EPHEMERAL_TYPES: frozenset[str] = frozenset(
    {
        "operational_fact",
        "project_status",
        "visual_observation",
        "next_step",
        "summary",
        "observation",
    }
)


def is_durable_type(knowledge_type: str) -> bool:
    """True quando o tipo de conhecimento é imune a staleness por tipo."""
    return (knowledge_type or "").strip().lower() in DURABLE_TYPES


def is_ephemeral_type(knowledge_type: str) -> bool:
    """True quando o tipo de conhecimento decai por TTL."""
    return (knowledge_type or "").strip().lower() in EPHEMERAL_TYPES


def access_immunity_threshold() -> int:
    """Número de acessos que imuniza um item contra staleness.

    `HIVE_STALENESS_ACCESS_IMMUNITY` (default 3). 0 desativa a imunidade por
    acesso (só a imunidade por tipo permanece).
    """
    raw = os.environ.get("HIVE_STALENESS_ACCESS_IMMUNITY", "3")
    try:
        threshold = int(raw)
    except ValueError:
        return 3
    return max(threshold, 0)


def is_access_immune(access_count: Any, threshold: int | None = None) -> bool:
    """True quando o contador de acessos já imunizou o item.

    `access_count` pode vir do metadata do item (`access_count` ou
    `governance.access_count`) ou de uma coluna futura. Ausência/não-numérico
    é tratado como 0 (não imune).
    """
    threshold = threshold if threshold is not None else access_immunity_threshold()
    if threshold <= 0:
        return False
    try:
        count = int(access_count or 0)
    except (TypeError, ValueError):
        return False
    return count >= threshold


def should_apply_staleness(
    *,
    knowledge_type: str,
    access_count: Any = None,
) -> bool:
    """Decide se a penalidade de staleness deve ser aplicada ao item.

    Regra (combinando as duas imunidades do OmniRoute):

      1. Tipo durável → imune por tipo, nunca penaliza por TTL.
      2. Tipo efêmero com `access_count >= threshold` → imune por acesso.
      3. Caso contrário (efêmero sem acesso suficiente) → penaliza.

    Tipos desconhecidos (fora de ambas as listas) são tratados como efêmeros:
    comportamento conservador — conteúdo não classificado decai em vez de
    persistir indefinidamente.
    """
    if is_durable_type(knowledge_type):
        return False
    if is_access_immune(access_count):
        return False
    return True
