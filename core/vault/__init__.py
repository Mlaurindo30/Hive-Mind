"""Camada canônica única de escrita no vault (FASE 0, 2026-08-12).

Este módulo impõe o contrato de anatomia do cerebro na RAIZ: todo artefato
escrito no vault passa por aqui, e o padrão correto deixa de ser "lembrado" por
cada escritor para ser **imposto** pela única função que escreve.

Três responsabilidades:

  1. ``vault_project_dir`` — resolve o DIRETÓRIO de projeto no vault a partir do
     `project_id` canônico. O `project_id` é rico (ex.: ``git/repo-hash``,
     ``root/label-hash``, ``local/hash``, ``unclassified/provider`` — ver
     ``hive_mind/projects/identity.py``), mas o diretório no lobo temporal usa o
     NOME canônico COM hash, SEM o prefixo de source-type. Isso elimina o
     aninhamento triplo (``git/repo-hash/tópico/neuronio``) que fragmentava 70%
     do vault: o contrato é ``<projeto>/<tópico>/neuronio-*.md`` (2 níveis).

  2. ``canonical_slug`` — normalização idempotente e ÚNICA de slug. Elimina a
     duplicação de tópicos por inconsistência de sanitização
     (``code_inspection`` vs ``codeinspection`` vs ``code inspection``).

  3. ``write_vault_note`` — o ÚNICO escritor de ``.md`` do vault. Garante
     frontmatter + seção ``## Sinapses`` com wikilinks ``[[...]]`` em TODO
     arquivo — resolve os links parciais na raiz (neurônios tinham, mas
     decisões/trabalho/templates não).

TODOS os escritores (materialize.py, dream_cycle, decision_promoter,
work_tracker, project_synthesizer, daily_writer, weekly/monthly/yearly
synthesizer) devem usar estas funções. Nenhum deles escreve ``.md`` direto.
"""
from __future__ import annotations

import re
from pathlib import Path

# Prefixos de source-type usados pelo ProjectIdentityResolver (identity.py).
# O diretório de projeto no vault é a ÚLTIMA parte (nome + hash), sem o prefixo.
_SOURCE_TYPE_PREFIXES = ("git/", "root/", "local/", "unclassified/")

# Sanitização de slug: caracteres não-alfanuméricos colapsam para "-", e o
# resultado é minúsculo. Hífen E underscore E espaço viram o MESMO separador,
# então "code-inspection", "code_inspection" e "code inspection" → "code-inspection".
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")


def vault_project_dir(project_id: str) -> str:
    """Resolve o diretório de projeto no vault a partir do `project_id` canônico.

    ``git/moneyprinterturbo-83ef01772a6d`` → ``moneyprinterturbo-83ef01772a6d``
    ``root/agent-corporativo-596377768abf`` → ``agent-corporativo-596377768abf``
    ``unclassified/legacy`` → ``legacy``
    ``hive-mind`` → ``hive-mind`` (sem prefixo, retorna como está)

    Mantém o hash no nome (decisão 2026-08-12) para evitar colisão entre dois
    repositórios de mesmo nome em source-types diferentes.
    """
    pid = (project_id or "").strip().strip("/")
    if not pid:
        return "unclassified"
    # Remove o prefixo de source-type (git/, root/, local/, unclassified/).
    for prefix in _SOURCE_TYPE_PREFIXES:
        if pid.startswith(prefix):
            pid = pid[len(prefix):]
            break
    # Ainda pode ter barra interna (ex.: monorepo "org/repo")? Mantém a última parte.
    return pid.split("/")[-1].strip().strip("/") or "unclassified"


def canonical_slug(text: str, max_len: int = 64) -> str:
    """Normaliza `text` para um slug canônico idempotente.

    ``canonical_slug(canonical_slug(x)) == canonical_slug(x)`` sempre.
    """
    s = _NON_SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return s[:max_len].rstrip("-")


def project_display_name(project_id: str) -> str:
    """Nome de exibição humano do projeto (frontmatter `project`/`project_name`).

    Mantém o hash intocado: ``moneyprinterturbo-83ef01772a6d`` →
    ``Moneyprinterturbo-83ef01772a6d``. A última parte (hash hex) não é title-cased.
    """
    d = vault_project_dir(project_id)
    # Separa o nome do sufixo de hash (ex.: "-83ef01772a6d", composto por hex).
    parts = d.split("-")
    # O hash é a última sequência puramente hexa de comprimento >= 8.
    if len(parts) >= 2 and _is_hex(parts[-1]) and len(parts[-1]) >= 8:
        name = " ".join(parts[:-1]).title()
        return f"{name}-{parts[-1]}"
    return d.replace("-", " ").strip().title()


def _is_hex(s: str) -> bool:
    return bool(s) and all(c in "0123456789abcdef" for c in s)


def write_vault_note(
    path: Path,
    *,
    frontmatter: dict[str, object],
    body: str,
    sinapses: list[str] | None = None,
    aliases: list[str] | None = None,
) -> Path:
    """Escreve UM arquivo ``.md`` no vault com frontmatter + Sinapses.

    ``frontmatter``: dict de chaves → valor (str/list). Serializado como YAML
    simples (chave: valor; listas em bloco). ``sinapses``: lista de strings de
    wikilinks para a seção ``## Sinapses`` (ex.: ``"projeto:: [[x]]"``).
    ``aliases``: lista de aliases (frontmatter `aliases`).

    Garante que TODO arquivo escrito no vault tenha a seção ``## Sinapses`` com
    wikilinks — o contrato de enriquecimento para agentes (graph traversal).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"- {item}")
        elif value is None:
            continue
        else:
            lines.append(f"{key}: {value}")
    if aliases:
        lines.append("aliases:")
        for a in aliases:
            lines.append(f"- {a}")
    lines.append("---")
    lines.append("")

    if body:
        lines.append(body.rstrip("\n"))
        lines.append("")

    if sinapses:
        lines.append("## Sinapses")
        for s in sinapses:
            lines.append(f"- {s}")
        lines.append("")

    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return path


def neuron_sinapses(project_dir: str, topic: str) -> list[str]:
    """Sinapses canônicas de um neurônio (projeto, tópico, lobo, córtex)."""
    return [
        f"projeto:: [[{project_dir}]]",
        f"tópico:: [[{topic}]]",
        "lobo:: [[cortex-temporal]]",
        "córtex:: [[cortex]]",
    ]
