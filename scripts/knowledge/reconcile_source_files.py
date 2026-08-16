"""Reconcilia neurons.source_file com o novo layout do vault (pós-achatamento).

Após o normalize_vault.py mover os neurônios, os source_file no DB apontam para
caminhos antigos. Este script reconstrói o source_file correto a partir do
workspace_id (project_id) + metadata (topic) + hash, resolvendo via a camada
canônica (core/vault). Neurônios cujo arquivo não existe mais são deixados com
source_file NULL para que o materializador os recrie.

Uso: python scripts/knowledge/reconcile_source_files.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent.parent
sys.path.insert(0, str(ROOT))

from core import paths as cp
from core.database import get_connection
from core.knowledge.materialize import _derive_topic
from core.vault import canonical_slug, vault_project_dir


def _build_hash_index() -> dict[str, Path]:
    """Constrói um índice hash_short → path de TODOS os neurônios do vault (uma vez)."""
    index: dict[str, Path] = {}
    for f in cp.TEMPORAL.rglob("neuronio-*.md"):
        # hash_short são os últimos 8 chars antes de ".md" (após o último "-").
        stem = f.stem  # neuronio-<slug>-<hash8>
        parts = stem.rsplit("-", 1)
        if len(parts) == 2 and len(parts[1]) == 8:
            index.setdefault(parts[1], f)
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcilia source_file pós-achatamento")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = get_connection()
    try:
        # O trigger neurons_after_update reindexa search_fts (FTS5) a cada UPDATE,
        # tornando cada UPDATE ~60ms. A reconciliação só muda source_file/topic —
        # que NÃO são indexados pelo FTS (só label/content são). Desabilitamos o
        # trigger durante a reconciliação e o reabilitamos no final; o FTS não
        # perde nada porque label/content ficam intocados.
        conn.execute("DROP TRIGGER IF EXISTS neurons_after_update")
        conn.commit()
        _trigger_disabled = True

        rows = conn.execute("""
            SELECT id, label, type, content, hash, metadata, workspace_id, topic, source_file
            FROM neurons
        """).fetchall()

        # Índice único de hash → path (evita rglob por neurônio).
        hash_index = _build_hash_index()

        fixed = 0
        stale_cleared = 0
        COMMIT_BATCH = 500
        since_commit = 0
        processed = 0
        for row in rows:
            src = row["source_file"]
            if not src:
                continue
            processed += 1
            p = Path(src)
            if not p.is_absolute():
                p = cp.SINAPSE_HOME / p
            if p.exists():
                continue  # já aponta para arquivo real
            # stale → resolve por hash (O(1))
            hash_short = (str(row["hash"] or "")[:16] or "")[:8]
            new = hash_index.get(hash_short)
            if new is not None:
                rel = str(new.relative_to(cp.SINAPSE_HOME))
                if not args.dry_run:
                    conn.execute(
                        "UPDATE neurons SET source_file = ?, topic = ? WHERE id = ?",
                        (rel, canonical_slug(_derive_topic(row["metadata"])), row["id"]),
                    )
                    since_commit += 1
                    if since_commit >= COMMIT_BATCH:
                        conn.commit()
                        since_commit = 0
                fixed += 1
            else:
                # arquivo não encontrado → limpa source_file para re-materializar
                if not args.dry_run:
                    conn.execute("UPDATE neurons SET source_file = NULL WHERE id = ?", (row["id"],))
                    since_commit += 1
                    if since_commit >= COMMIT_BATCH:
                        conn.commit()
                        since_commit = 0
                stale_cleared += 1

        if not args.dry_run and since_commit:
            conn.commit()
        # Reabilita o trigger FTS (label/content intocados — índice permanece válido).
        if not args.dry_run:
            conn.execute("""
                CREATE TRIGGER neurons_after_update AFTER UPDATE ON neurons BEGIN
                    DELETE FROM search_fts WHERE neuron_id = old.id;
                    INSERT INTO search_fts(neuron_id, label, content)
                    VALUES (new.id, new.label, new.content);
                END
            """)
            conn.commit()
        print(f"fixed (re-apontados): {fixed}")
        print(f"stale_cleared (source_file=NULL): {stale_cleared}")
        print(f"processed: {processed}")
        if args.dry_run:
            print("[dry-run] nada foi escrito")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
