#!/usr/bin/env python3
"""Hot-backup periódico dos bancos SQLite críticos.

Usa sqlite3.Connection.backup() — cópia consistente mesmo com o banco em uso.
Cada backup recebe timestamp ISO; retenção é feita aqui (keep_last).
Hermes (~/.hermes/state.db, 150MB+) é excluído por padrão por ser grande demais
para backup diário — use SINAPSE_BACKUP_HERMES=1 para incluir.

Saída:
  OK   claude-mem  32.1MB  → ~/.claude-mem/backups/claude-mem.2026-06-21.db
  SKIP hive_mind   source not found
  ...
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

HOME = Path.home()
ROOT = Path(__file__).resolve().parents[2]
TIMESTAMP = time.strftime("%Y-%m-%d")


@dataclass
class Target:
    name: str
    src: Path
    dest_dir: Path
    keep_last: int = 7
    enabled: bool = True


def _targets() -> list[Target]:
    targets = [
        Target(
            name="claude-mem",
            src=HOME / ".claude-mem" / "claude-mem.db",
            dest_dir=HOME / ".claude-mem" / "backups",
            keep_last=7,
        ),
        Target(
            name="hive_mind",
            src=ROOT / "hive_mind.db",
            dest_dir=ROOT / "backups",
            keep_last=7,
        ),
        Target(
            name="swarmclaw",
            src=HOME / ".swarmclaw" / "data" / "swarmclaw.db",
            dest_dir=HOME / ".swarmclaw" / "backups",
            keep_last=7,
        ),
        Target(
            name="hermes",
            src=HOME / ".hermes" / "state.db",
            dest_dir=HOME / ".hermes" / "backups",
            keep_last=3,
            enabled=bool(os.environ.get("SINAPSE_BACKUP_HERMES")),
        ),
    ]
    return targets


def _fmt_mb(path: Path) -> str:
    try:
        return f"{path.stat().st_size / 1_048_576:.1f}MB"
    except OSError:
        return "?"


def _hot_backup(src: Path, dest: Path) -> float:
    """Copia src → dest usando a API nativa do sqlite3 (seguro com DB em uso)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=10)
    dst_con = sqlite3.connect(str(dest))
    try:
        src_con.backup(dst_con, pages=512)
    finally:
        dst_con.close()
        src_con.close()
    return time.monotonic() - t0


def _prune(dest_dir: Path, name: str, keep_last: int) -> list[Path]:
    pattern = f"{name}.20*.db"
    existing = sorted(dest_dir.glob(pattern), key=lambda p: p.name)
    to_delete = existing[:-keep_last] if keep_last > 0 else []
    for path in to_delete:
        path.unlink(missing_ok=True)
    return to_delete


@dataclass
class Result:
    name: str
    status: str
    detail: str
    pruned: list[str] = field(default_factory=list)


def backup_target(t: Target) -> Result:
    if not t.enabled:
        return Result(t.name, "SKIP", "disabled (set SINAPSE_BACKUP_HERMES=1 to enable)")
    if not t.src.exists():
        return Result(t.name, "SKIP", "source not found")

    dest = t.dest_dir / f"{t.name}.{TIMESTAMP}.db"

    # Não re-faz o backup se já existe para hoje
    if dest.exists():
        return Result(t.name, "OK", f"already done today → {dest} ({_fmt_mb(dest)})")

    try:
        elapsed = _hot_backup(t.src, dest)
    except Exception as exc:
        return Result(t.name, "FAIL", str(exc))

    pruned = _prune(t.dest_dir, t.name, t.keep_last)
    return Result(
        t.name,
        "OK",
        f"{_fmt_mb(t.src)} → {dest} ({elapsed:.1f}s)",
        pruned=[str(p) for p in pruned],
    )


def run(targets: list[Target]) -> dict:
    results = [backup_target(t) for t in targets]
    failures = [r for r in results if r.status == "FAIL"]
    return {
        "timestamp": TIMESTAMP,
        "results": [
            {"name": r.name, "status": r.status, "detail": r.detail, "pruned": r.pruned}
            for r in results
        ],
        "healthy": not failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hot-backup dos bancos SQLite críticos.")
    parser.add_argument("--json", action="store_true", help="saída JSON")
    parser.add_argument("--keep", type=int, default=None,
                        help="override de retenção (padrão por target)")
    args = parser.parse_args(argv)

    targets = _targets()
    if args.keep is not None:
        for t in targets:
            t.keep_last = args.keep

    report = run(targets)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Database Backup — {report['timestamp']}")
        for r in report["results"]:
            print(f"  {r['status']:4} {r['name']:12} {r['detail']}")
            for p in r.get("pruned", []):
                print(f"       pruned: {p}")

    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
