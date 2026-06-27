#!/usr/bin/env python3
"""
sqlite_wal_recovery.py — Auto-recuperação do SQLite WAL para claude-mem.db.

Uso:
    python3 scripts/health/sqlite_wal_recovery.py [--check] [--fix]

Sem argumentos: executa --fix automaticamente.
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path.home() / ".claude-mem" / "claude-mem.db"
WAL_PATH = Path(str(DB_PATH) + "-wal")
SHM_PATH = Path(str(DB_PATH) + "-shm")
LOCK_PATH = Path.home() / ".claude-mem" / "tailer.lock"
MAX_WAL_MB = 50  # WAL maior que isso = suspeito de crescimento descontrolado


def check() -> dict:
    status = {"db_exists": DB_PATH.exists(), "wal_size_mb": 0, "shm_size_mb": 0,
              "wal_suspicious": False, "lock_orphan": False, "worker_running": False}
    if DB_PATH.exists():
        status["db_size_mb"] = DB_PATH.stat().st_size // (1024 * 1024)
        if WAL_PATH.exists():
            wal_mb = WAL_PATH.stat().st_size / (1024 * 1024)
            status["wal_size_mb"] = round(wal_mb, 2)
            status["wal_suspicious"] = wal_mb > MAX_WAL_MB
        if SHM_PATH.exists():
            status["shm_size_mb"] = round(SHM_PATH.stat().st_size / (1024 * 1024), 2)
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text().strip())
            os.kill(pid, 0)
            status["lock_pid_alive"] = True
        except (ValueError, OSError, ProcessLookupError):
            status["lock_orphan"] = True
    return status


def fix() -> list:
    actions = []
    s = check()

    # 1. Remover lock órfão
    if s.get("lock_orphan"):
        LOCK_PATH.unlink(missing_ok=True)
        actions.append("🗑️  tailer.lock órfão removido")

    # 2. Checkpoint WAL → main DB
    if DB_PATH.exists():
        con = sqlite3.connect(str(DB_PATH), timeout=60)
        try:
            con.execute("PRAGMA busy_timeout=60000")
            result = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            pages_total = result[0]
            pages_spilled = result[1]
            if pages_total > 0:
                actions.append(f"✅ WAL checkpoint: {pages_spilled}/{pages_total} páginas escritas ao DB principal")
            # 3. VACUUM leve se WAL estava suspeito
            if s.get("wal_suspicious"):
                con.execute("VACUUM")
                actions.append(f"🔧 VACUUM executado (WAL estava com {s['wal_size_mb']:.1f}MB)")
            # 4. reportar saúde
            tables = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            actions.append(f"📊 {tables} tabelas, DB {s.get('db_size_mb', '?')}MB")
        except Exception as e:
            actions.append(f"❌ Erro no checkpoint: {e}")
        finally:
            con.close()

    if not actions:
        actions.append("✅ Nenhuma ação necessária — DB saudável")
    return actions


def main():
    parser = argparse.ArgumentParser(description="Auto-recuperação WAL do claude-mem.db")
    parser.add_argument("--check", action="store_true", help="Apenas diagnostica")
    parser.add_argument("--fix", action="store_true", help="Aplica correções")
    args = parser.parse_args()

    if args.check:
        s = check()
        for k, v in s.items():
            print(f"  {k}: {v}")
        if s.get("wal_suspicious"):
            print("\n⚠️  WAL suspeito! Rode com --fix")
            sys.exit(1)
        return

    if not args.fix:
        # Sem argumentos: executa fix automaticamente
        actions = fix()
    else:
        actions = fix()

    print("=== sqlite_wal_recovery ===")
    for a in actions:
        print(f"  {a}")
    print("=== pronto ===")


if __name__ == "__main__":
    main()
