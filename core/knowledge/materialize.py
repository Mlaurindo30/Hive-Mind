"""Materialização determinística de neurônios órfãos em .md no vault.

A promoção K3 (`promote_pending_observations` → `_promote_to_neuron`) grava o
neurônio na tabela `neurons` do SQLite mas NÃO escreve o arquivo `.md` no vault
— a materialização `.md` era função exclusiva do Dream Cycle
(`_route_and_persist_project`), que só roda sobre `observations` (não sobre a
tabela `neurons`). Quando o K3 consome as observações antes do Dream Cycle, os
neurônios ficam órfãos de vault: existem no índice (SQLite) mas não na fonte
primária (`cerebro/cortex/temporal/`).

Este módulo fecha esse gap de forma determinística, SEM LLM:

  - `materialize_neuron()` — escreve UM neurônio como `.md` no vault, seguindo o
    frontmatter canônico (ADR-007), e devolve o `source_file` relativo.
  - `materialize_orphan_neurons()` — percorre os neurônios com
    `source_file IS NULL` e materializa em lote (commit por neurônio, resiliência
    a falha individual).

É o mesmo contrato do Dream Cycle para o formato do arquivo, mas a partir do
neurônio já tipado — não re-destila, não re-valida, apenas persiste o que já foi
promovido. O topic é derivado dos `concepts` do metadata (o primeiro concept é o
tópico primário); sem concepts, cai em "general".

Tipos efêmeros (`operational_fact`, `project_status`, `visual_observation`,
`next_step`, `summary`, `observation`) NÃO são materializados em `.md`: são
estado transitório e pertencem ao índice, não à fonte primária. Isso é coerente
com o typed decay (core/knowledge/typed_decay.py) — o ruído de sessão não
polui o vault.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core import paths as cp
from core.knowledge.typed_decay import EPHEMERAL_TYPES
from core.vault import (
    canonical_slug,
    neuron_sinapses,
    project_display_name,
    vault_project_dir,
    write_vault_note,
)

# Tipos que merecem materialização no vault (fonte primária). Os efêmeros ficam
# só no índice (SQLite) e decaem — nunca viram .md.
MATERIALIZABLE_TYPES = frozenset(
    {
        "fact",
        "decision",
        "learning",
        "preference",
        "rationale",
        "code_symbol",
        "document_chunk",
        "security_alert",
        "security_note",
        "sensitive",
    }
)


def _derive_topic(metadata_json: str | None) -> str:
    """Deriva o tópico primário a partir dos `concepts` do metadata.

    O claude-mem emite `concepts` (ex.: ["parallel-processing", ...]). O primeiro
    concept não-genérico vira o tópico; sem concepts, "general". A string retornada
    ainda é normalizada por `canonical_slug` no chamador.
    """
    concepts: list[str] = []
    if metadata_json:
        try:
            m = json.loads(metadata_json)
            cm = m.get("candidate_metadata", {}).get("concepts") or m.get("concepts")
            if isinstance(cm, list):
                concepts = [str(c) for c in cm if str(c).strip()]
        except (json.JSONDecodeError, AttributeError):
            pass
    return concepts[0] if concepts else "general"


def materialize_neuron(conn: sqlite3.Connection, neuron: dict[str, Any]) -> str | None:
    """Escreve UM neurônio como .md no vault e devolve o `source_file` relativo.

    Não re-tipa, não re-valida: o neurônio já passou pelo intake/promoção. Retorna
    `None` se o tipo não é materializável (efêmero) ou se não há conteúdo.
    """
    ntype = str(neuron.get("type") or "")
    if ntype not in MATERIALIZABLE_TYPES:
        return None

    content = str(neuron.get("content") or "").strip()
    label = str(neuron.get("label") or "").strip()
    if not content and not label:
        return None

    workspace_id = str(neuron.get("workspace_id") or "default").strip() or "default"
    # FASE 0 (2026-08-12): o diretório de projeto no vault é resolvido pela camada
    # canônica (core/vault), NÃO pelo project_id cru. project_id rico
    # (ex.: "git/repo-hash") não pode virar path de diretório — criaria aninhamento
    # triplo. vault_project_dir remove o prefixo de source-type e mantém nome+hash.
    project_id = workspace_id
    project_dir = vault_project_dir(project_id)
    project_name = project_display_name(project_id)

    topic = canonical_slug(_derive_topic(neuron.get("metadata")))
    integrity_hash = str(neuron.get("hash") or "")[:16]
    if not integrity_hash:
        import hashlib
        integrity_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    slug = canonical_slug(label)
    hash_short = integrity_hash[:8]
    nid = f"neuronio-{slug}-{hash_short}" if slug else f"neuronio-{hash_short}"

    now = datetime.now()

    note_file = cp.TEMPORAL / project_dir / topic / f"{nid}.md"
    write_vault_note(
        note_file,
        frontmatter={
            "type": ntype,
            "project": project_name,
            "project_id": project_id,
            "project_name": project_name,
            "identity_source": "canonical",
            "topic": topic,
            "integrity_hash": integrity_hash,
            "last_updated": now.strftime("%Y-%m-%d %H:%M"),
            "source": "knowledge-promotion",
        },
        body=f"# {label or nid}\n\n{content}",
        sinapses=neuron_sinapses(project_dir, topic),
    )

    source_rel = str(note_file.relative_to(cp.SINAPSE_HOME)) if hasattr(cp, "SINAPSE_HOME") else str(note_file)
    return source_rel


def materialize_orphan_neurons(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Materializa neurônios com `source_file IS NULL` em .md no vault.

    Percorre a tabela `neurons`, escreve o .md de cada neurônio materializável e
    atualiza `source_file` + `topic` no DB. Cada neurônio é commitado em
    isolamento para que uma falha não derrube o lote inteiro.

    Retorna o relatório: total varrido, materializado, ignorado (efêmero/sem
    conteúdo) e falhas.
    """
    report = {"scanned": 0, "materialized": 0, "skipped": 0, "failed": 0}

    sql = """
        SELECT id, label, type, content, hash, metadata, workspace_id, topic
        FROM neurons
        WHERE source_file IS NULL OR source_file = ''
    """
    if limit:
        sql += " LIMIT ?"
        rows = conn.execute(sql, (limit,)).fetchall()
    else:
        rows = conn.execute(sql).fetchall()

    report["scanned"] = len(rows)
    # Commit em lote (a cada COMMIT_BATCH) em vez de por neurônio: o commit
    # individual por neurônio fazia o materializador rodar a ~4 arquivos/s;
    # em lote, a escrita do vault domina e o SQLite só sincroniza a cada N.
    COMMIT_BATCH = 500
    since_commit = 0
    for row in rows:
        neuron = dict(row)
        try:
            source_rel = materialize_neuron(conn, neuron)
            if source_rel is None:
                report["skipped"] += 1
                continue
            if not dry_run:
                topic = _derive_topic(neuron.get("metadata"))
                conn.execute(
                    "UPDATE neurons SET source_file = ?, topic = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (source_rel, topic, neuron["id"]),
                )
                since_commit += 1
                if since_commit >= COMMIT_BATCH:
                    conn.commit()
                    since_commit = 0
            report["materialized"] += 1
        except Exception:
            report["failed"] += 1
            try:
                conn.rollback()
            except Exception:
                pass

    if not dry_run and since_commit:
        conn.commit()
    return report
