#!/usr/bin/env python3
"""Backfill de review_date/next_review nas notas curadas do vault (F3).

Adiciona os campos de validade temporal ao frontmatter de notas que ainda não
os têm, nas áreas curadas (cortex/frontal e cerebelo). A data-base é o último
commit git do arquivo — não o mtime, que o Syncthing pode alterar sem mudança
de conteúdo. Notas sem histórico git usam a data de hoje.

Idempotente: notas que já têm review_date são puladas.

Uso:
    python3 scripts/maintenance/backfill_review_dates.py --dry-run
    python3 scripts/maintenance/backfill_review_dates.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

REVIEW_TTL_DAYS = 90
CURATED_DIRS = ("cerebro/cortex/frontal", "cerebro/cerebelo")


def _git_last_commit_date(path: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(path)],
            capture_output=True, text=True, cwd=ROOT, timeout=10,
        )
        value = out.stdout.strip()
        return value or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    """(bloco_yaml, resto) ou None quando não há frontmatter."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


def backfill(*, apply: bool) -> dict:
    report = {"scanned": 0, "updated": 0, "skipped_has_review": 0,
              "skipped_no_frontmatter": 0, "dry_run": not apply}
    for rel in CURATED_DIRS:
        root = ROOT / rel
        if not root.exists():
            continue
        for md_file in root.rglob("*.md"):
            if ".sync-conflict-" in md_file.name:
                continue
            report["scanned"] += 1
            text = md_file.read_text(encoding="utf-8", errors="ignore")
            split = _split_frontmatter(text)
            if split is None:
                report["skipped_no_frontmatter"] += 1
                continue
            yaml_block, body = split
            if "review_date:" in yaml_block:
                report["skipped_has_review"] += 1
                continue
            base = _git_last_commit_date(md_file) or datetime.now().strftime("%Y-%m-%d")
            next_review = (
                datetime.strptime(base, "%Y-%m-%d") + timedelta(days=REVIEW_TTL_DAYS)
            ).strftime("%Y-%m-%d")
            new_yaml = yaml_block.rstrip("\n") + (
                f"\nreview_date: {base}\nnext_review: {next_review}\n"
            )
            if apply:
                md_file.write_text(f"---{new_yaml}---{body}", encoding="utf-8")
            report["updated"] += 1
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostra o que mudaria sem escrever.")
    args = parser.parse_args()
    report = backfill(apply=not args.dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
