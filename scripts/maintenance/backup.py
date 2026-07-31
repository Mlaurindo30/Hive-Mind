"""Hive-Mind scheduled backup entrypoint.

The Windows Task Scheduler job ``HiveMind-Backup`` (registered by
``scripts/setup/register-windows-jobs.ps1``) invokes this module once per
day. The real audit + retention logic lives in
``scripts/health/backup_audit.py``; this wrapper exists so the scheduler has
a single canonical Python target and so audit + prune run together with one
log artifact per execution.

Usage:
    python scripts/maintenance/backup.py [--apply] [--json] [--root <path>]

The default mode is read-only: it reports which files would be pruned and
which secret-hits exist, but does not touch the filesystem. Pass ``--apply``
to actually remove stale artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the repo importable when invoked directly via Task Scheduler.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.health import backup_audit  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=_REPO_ROOT,
        help="Hive-Mind repository root (default: parent of this file's grandparent).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually prune stale artifacts (default: report only).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=_REPO_ROOT / "logs" / "backup",
        help="Directory where execution log artifacts are written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()

    audit_args = argparse.Namespace(
        root=root,
        keep_umc=10,
        keep_component_lock=20,
        keep_session_logs=10,
        keep_fk_repair=5,
        keep_legacy_per_family=1,
        legacy_max_age_days=30,
        apply=args.apply,
        json=args.json,
    )
    report = backup_audit.run_audit(root, audit_args)
    removed = backup_audit.apply_prune(report) if args.apply else None

    log_dir: Path = args.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    log_path = log_dir / f"backup-{stamp}.json"
    payload = dict(report)
    if removed is not None:
        payload["removed"] = removed
    payload["applied"] = bool(args.apply)
    log_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(backup_audit._human_summary(report, removed=removed))  # noqa: SLF001
        print(f"log: {log_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
