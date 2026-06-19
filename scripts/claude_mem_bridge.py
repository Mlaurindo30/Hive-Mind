#!/usr/bin/env python3
"""
scripts/claude_mem_bridge.py — Ponte claude-mem.db → hive_mind.db (Memória Viva).

PROBLEMA QUE RESOLVE (doc 08): o `dream_cycle` lê `hive_mind.db.observations`, mas o
trabalho real multi-projeto vive em `claude-mem.db` (com `project` correto). Não havia
ponte → o dream só via entulho com `project` NULL e colapsava tudo em "Hive-Mind".

Esta ponte importa as observações do claude-mem para o hive_mind PRESERVANDO `project`,
de forma idempotente (id determinístico `cm-{content_hash}` + INSERT OR IGNORE). O dream
continua lendo o hive_mind e usando `archived` como marcador de já-consolidado — código
do dream intacto. Sem LLM, sem load_env (R3).

Uso:
  python scripts/claude_mem_bridge.py                 # importa novas + quarentena legado
  python scripts/claude_mem_bridge.py --dry-run       # só conta, não escreve
  python scripts/claude_mem_bridge.py --no-quarantine # importa sem mexer no legado
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
ROOT = _HERE.parent

from core.database import get_connection, ensure_migrations  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("claude_mem_bridge")

CLAUDE_MEM_DB = Path(os.environ.get(
    "CLAUDE_MEM_DB", str(Path.home() / ".claude-mem" / "claude-mem.db")))
DEFAULT_LIMIT = 1000            # boundedness (R8): teto de obs importadas por execução
BRIDGE_SOURCE = "claude-mem-bridge"


def _content_hash(row) -> str:
    """Hash estável da observação p/ id determinístico (usa o do claude-mem se houver)."""
    h = row["content_hash"] if "content_hash" in row.keys() and row["content_hash"] else None
    if h:
        return str(h)
    base = f"{row['project']}|{row['title']}|{row['text']}"
    return hashlib.sha256(base.encode("utf-8", "ignore")).hexdigest()[:24]


def open_claude_mem(db_path: Path = CLAUDE_MEM_DB) -> sqlite3.Connection:
    """Abre o claude-mem.db em modo read-only (não tocamos a fonte)."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_source_observations(cm_conn, *, limit: Optional[int] = None) -> list:
    """Lê observations do claude-mem (mais antigas primeiro p/ o dream consumir em ordem)."""
    sql = ("SELECT id, project, text, narrative, title, type, created_at, "
           "created_at_epoch, content_hash FROM observations "
           "ORDER BY created_at_epoch ASC")
    if limit:
        sql += f" LIMIT {int(limit)}"
    return cm_conn.execute(sql).fetchall()


def existing_bridged_ids(hm_conn) -> set:
    """ids já importados (cm-*) — p/ pular sem depender de exceção."""
    return {r[0] for r in hm_conn.execute(
        "SELECT id FROM observations WHERE id LIKE 'cm-%'")}


def bridge(*, cm_db: Path = CLAUDE_MEM_DB, limit: int = DEFAULT_LIMIT,
           dry_run: bool = False, default_project: str = "Hive-Mind") -> dict:
    """Importa observations do claude-mem → hive_mind preservando project. Idempotente."""
    if not cm_db.exists():
        logger.warning("claude-mem.db não encontrado em %s — nada a importar.", cm_db)
        return {"scanned": 0, "inserted": 0, "skipped": 0}
    hm = get_connection()
    ensure_migrations(hm)
    cm = open_claude_mem(cm_db)
    try:
        already = existing_bridged_ids(hm)
        rows = fetch_source_observations(cm, limit=limit)
        inserted = skipped = 0
        for r in rows:
            det_id = f"cm-{_content_hash(r)}"
            if det_id in already:
                skipped += 1
                continue
            content = (r["text"] or r["narrative"] or "").strip()
            if not content:
                skipped += 1
                continue
            project = (r["project"] or "").strip() or default_project
            meta = json.dumps({"source": BRIDGE_SOURCE, "cm_id": r["id"],
                               "cm_epoch": r["created_at_epoch"]})
            if not dry_run:
                hm.execute(
                    """INSERT OR IGNORE INTO observations
                       (id, project, type, title, content, created_at, archived, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                    (det_id, project, r["type"] or "event",
                     r["title"] or "(sem título)", content, r["created_at"], meta))
            already.add(det_id)
            inserted += 1
        if not dry_run:
            hm.commit()
        stats = {"scanned": len(rows), "inserted": inserted, "skipped": skipped}
        logger.info("bridge: %s", stats)
        return stats
    finally:
        cm.close()
        hm.close()


def quarantine_legacy(*, dry_run: bool = False) -> int:
    """Marca como archived=2 (quarentena) o entulho legado: obs SEM project, NÃO-bridged,
    ainda pendentes (archived=0). Evita que o dream gere neurônios-lixo em Hive-Mind."""
    hm = get_connection()
    try:
        where = ("project IS NULL AND id NOT LIKE 'cm-%' AND archived = 0")
        n = hm.execute(f"SELECT COUNT(*) FROM observations WHERE {where}").fetchone()[0]
        if not dry_run and n:
            hm.execute(f"UPDATE observations SET archived = 2 WHERE {where}")
            hm.commit()
        logger.info("quarentena legado: %d obs (dry_run=%s)", n, dry_run)
        return n
    finally:
        hm.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Ponte claude-mem.db → hive_mind.db.")
    ap.add_argument("--dry-run", action="store_true", help="conta, não escreve")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--no-quarantine", action="store_true",
                    help="não quarentena o entulho legado")
    args = ap.parse_args()
    bridge(limit=args.limit, dry_run=args.dry_run)
    if not args.no_quarantine:
        quarantine_legacy(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
