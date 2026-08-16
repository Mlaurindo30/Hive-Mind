#!/usr/bin/env python3
"""Materializa neurônios órfãos (sem .md no vault) a partir da tabela neurons.

P0 (2026-08-12): fecha o gap em que a promoção K3 criou 56k+ neurônios no SQLite
sem escrever o .md no cerebro. Este script percorre a tabela `neurons`, escreve o
.md de cada neurônio materializável e atualiza `source_file` no DB.

Uso:
    python scripts/knowledge/materialize_neurons.py --dry-run      # conta sem escrever
    python scripts/knowledge/materialize_neurons.py                # materializa tudo
    python scripts/knowledge/materialize_neurons.py --limit 1000   # lote parcial
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from core.database import get_connection
from core.knowledge.materialize import materialize_orphan_neurons


def main() -> int:
    parser = argparse.ArgumentParser(description="Materializa neurônios órfãos em .md no vault")
    parser.add_argument("--dry-run", action="store_true", help="conta sem escrever")
    parser.add_argument("--limit", type=int, default=None, help="limita o número de neurônios")
    args = parser.parse_args()

    conn = get_connection()
    report = materialize_orphan_neurons(conn, limit=args.limit, dry_run=args.dry_run)
    conn.close()

    print(f"scanned:      {report['scanned']}")
    print(f"materialized: {report['materialized']}")
    print(f"skipped:      {report['skipped']} (efêmero/sem conteúdo)")
    print(f"failed:       {report['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
