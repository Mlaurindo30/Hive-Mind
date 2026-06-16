#!/usr/bin/env python3
"""
capture_maintenance.py — Manutenção periódica SEM perda de memória.

A "memória" (observations / user_prompts / session_summaries / vetores) NUNCA é
apagada por este script. Ele só:

  1. compact_db   → claude-mem.db: wal_checkpoint(TRUNCATE) + VACUUM + ANALYZE.
                    Apenas COMPACTA (mesmos dados, menos espaço/ WAL enxuto).
  2. gc_state     → capture-state/<tool>.json: remove o RASCUNHO de dedup
                    (hashes `seen`) de sessões inativas há mais de
                    RETENTION_DAYS — já fora da janela de reparse (2h), nunca
                    mais lidas. Isso é bookkeeping morto, NÃO é memória.
  3. prune_backups→ remove .bak/backups antigos (> BACKUP_KEEP_DAYS).

Idempotente e seguro p/ rodar com o worker no ar (usa busy_timeout).
Pensado p/ disparo semanal (systemd timer / cron).
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import time
from pathlib import Path

HOME = Path.home()
DATA_DIR = Path(os.environ.get("CLAUDE_MEM_DATA_DIR", str(HOME / ".claude-mem")))
DB = DATA_DIR / "claude-mem.db"
STATE_DIR = DATA_DIR / "capture-state"
BACKUP_DIR = DATA_DIR / "backups"

# Sessão sem atividade há mais de N dias → seu rascunho de dedup é lixo (a janela
# de reparse do daemon é 2h; 14 dias é folgadíssimo). NÃO afeta a memória.
RETENTION_DAYS = int(os.environ.get("CAPTURE_STATE_RETENTION_DAYS", "14"))
BACKUP_KEEP_DAYS = int(os.environ.get("CLAUDE_MEM_BACKUP_KEEP_DAYS", "30"))


def compact_db() -> None:
    """Compacta o DB sem apagar dados: flush do WAL + VACUUM + ANALYZE."""
    if not DB.exists():
        print("  ⊘ DB não encontrado, pulando compactação")
        return
    con = sqlite3.connect(str(DB), timeout=30)
    try:
        con.execute("PRAGMA busy_timeout=30000")  # espera lock em vez de falhar
        size_before = DB.stat().st_size
        wal = Path(str(DB) + "-wal")
        wal_before = wal.stat().st_size if wal.exists() else 0
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("VACUUM")
        con.execute("ANALYZE")
        con.commit()
        size_after = DB.stat().st_size
        print(f"  ✓ DB compactado: {size_before//1024}K→{size_after//1024}K "
              f"(WAL {wal_before//1024}K esvaziado)")
    finally:
        con.close()


def gc_state() -> None:
    """Remove registros de dedup de sessões inativas há > RETENTION_DAYS.
    Mantém intacto tudo que ainda está dentro da janela de reparse."""
    cutoff = time.time() - RETENTION_DAYS * 86400
    total_removed = 0
    for f in glob.glob(str(STATE_DIR / "*.json")):
        if f.endswith(".tmp"):
            continue
        try:
            data = json.loads(Path(f).read_text())
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        before = len(data)
        kept = {}
        now = time.time()
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            ts = v.get("ts")
            if not isinstance(ts, (int, float)):
                # Sem `ts` = registro que ainda não foi tocado pelo código novo.
                # NÃO é seguro assumir morto (pode ser sessão viva) → mantém e
                # backfill ts=now, pra envelhecer a partir de agora.
                v["ts"] = int(now)
                kept[k] = v
            elif ts >= cutoff:
                kept[k] = v
            # else: tem ts e está velho → morto de verdade → descarta
        removed = before - len(kept)
        if removed:
            p = Path(f)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(kept, indent=2))
            tmp.replace(p)
            total_removed += removed
            print(f"  ✓ {p.name}: -{removed} dedup morto ({len(kept)} ativos)")
    print(f"  GC state: {total_removed} registros de dedup removidos "
          f"(0 memória perdida)")


def prune_backups() -> None:
    """Remove backups (.bak / backups/*.db) com mais de BACKUP_KEEP_DAYS dias."""
    cutoff = time.time() - BACKUP_KEEP_DAYS * 86400
    n = 0
    patterns = [str(DATA_DIR / "*.bak"), str(DATA_DIR / "*.bak-*"),
                str(BACKUP_DIR / "*.db")]
    for pat in patterns:
        for f in glob.glob(pat):
            try:
                if os.path.getmtime(f) < cutoff:
                    os.remove(f)
                    n += 1
            except OSError:
                pass
    print(f"  ✓ backups antigos removidos: {n} (mantém últimos {BACKUP_KEEP_DAYS}d)")


def main() -> int:
    print(f"[manutenção claude-mem] {time.strftime('%Y-%m-%d %H:%M:%S')}")
    gc_state()
    compact_db()
    prune_backups()
    print("  concluído — memória intacta, espaço recuperado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
