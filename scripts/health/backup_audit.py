#!/usr/bin/env python3
"""Audit and prune local backup artifacts with explicit retention policies."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
HOME = Path.home()


@dataclass(frozen=True)
class RetentionRule:
    name: str
    folder: Path
    pattern: str
    keep_last: int


def _repo_rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _dir_stats(directory: Path) -> dict:
    if not directory.exists():
        return {
            "exists": False,
            "files": 0,
            "bytes": 0,
            "newest": None,
            "oldest": None,
        }

    files = [p for p in directory.rglob("*") if p.is_file()]
    if not files:
        return {
            "exists": True,
            "files": 0,
            "bytes": 0,
            "newest": None,
            "oldest": None,
        }

    by_mtime = sorted(files, key=lambda p: p.stat().st_mtime)
    total_bytes = sum(p.stat().st_size for p in files)
    return {
        "exists": True,
        "files": len(files),
        "bytes": total_bytes,
        "newest": str(by_mtime[-1]),
        "oldest": str(by_mtime[0]),
    }


def _secret_hits(root: Path) -> list[dict]:
    secret_name = re.compile(r"(API_KEY|TOKEN|PASSWORD|SECRET)$")
    hits: list[dict] = []
    candidates = [
        *root.glob("backups/**/settings.json"),
        *root.glob("backups/**/.env"),
        *root.glob("backups/**/.env.*"),
    ]
    for file_path in candidates:
        if not file_path.is_file():
            continue
        if file_path.name.startswith(".env"):
            for line_number, raw in enumerate(file_path.read_text(errors="ignore").splitlines(), start=1):
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if not secret_name.search(key.strip()):
                    continue
                if value.strip().strip('"').strip("'"):
                    hits.append(
                        {
                            "file": str(file_path),
                            "line": line_number,
                            "key": key.strip(),
                            "kind": "env",
                        }
                    )
            continue

        try:
            payload = json.loads(file_path.read_text(errors="ignore"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            if not secret_name.search(key):
                continue
            if value.strip():
                hits.append(
                    {
                        "file": str(file_path),
                        "key": key,
                        "kind": "json",
                    }
                )
    return hits


def _stale_for_rule(rule: RetentionRule) -> list[Path]:
    if rule.keep_last < 1 or not rule.folder.exists():
        return []
    matches = sorted(rule.folder.glob(rule.pattern), key=lambda p: p.name)
    return matches[:-rule.keep_last]


def _legacy_dir_name_parts(name: str) -> tuple[str, str, str] | None:
    match = re.match(r"^(?P<family>.+)-(?P<date>\d{8})-(?P<time>\d{6})$", name)
    if not match:
        return None
    return match.group("family"), match.group("date"), match.group("time")


def _legacy_snapshot_candidates(root: Path, keep_per_family: int, max_age_days: int) -> list[Path]:
    backups_root = root / "backups"
    if not backups_root.exists() or keep_per_family < 1:
        return []

    families: dict[str, list[Path]] = {}
    for child in backups_root.iterdir():
        if not child.is_dir():
            continue
        parts = _legacy_dir_name_parts(child.name)
        if not parts:
            continue
        family, _, _ = parts
        families.setdefault(family, []).append(child)

    stale: list[Path] = []
    now = time.time()
    max_age_secs = max_age_days * 86400
    for _, dirs in families.items():
        ordered = sorted(dirs, key=lambda p: p.name)
        stale.extend(ordered[:-keep_per_family])
        if max_age_days > 0:
            for path in ordered:
                age = now - path.stat().st_mtime
                if age > max_age_secs and path not in stale:
                    stale.append(path)

    return sorted(stale, key=lambda p: p.name)


def _retention_rules(root: Path, args: argparse.Namespace) -> list[RetentionRule]:
    return [
        RetentionRule(
            name="umc_backups",
            folder=root / "backups",
            pattern="hive_mind.*.db",
            keep_last=args.keep_umc,
        ),
        RetentionRule(
            name="component_lock",
            folder=root / "config" / "component-lock-backups",
            pattern="components.lock.*.json",
            keep_last=args.keep_component_lock,
        ),
        RetentionRule(
            name="session_finalize",
            folder=root / "cerebro" / "thinking" / "session-logs",
            pattern="session_finalize_*.json",
            keep_last=args.keep_session_logs,
        ),
        RetentionRule(
            name="fk_repair",
            folder=root / "backups" / "fk-repair",
            pattern="claude-mem.before-fk-repair.*.db",
            keep_last=args.keep_fk_repair,
        ),
        RetentionRule(
            name="claude_mem_daily",
            folder=HOME / ".claude-mem" / "backups",
            pattern="claude-mem.20*.db",
            keep_last=7,
        ),
        RetentionRule(
            name="swarmclaw_daily",
            folder=HOME / ".swarmclaw" / "backups",
            pattern="swarmclaw.20*.db",
            keep_last=7,
        ),
        RetentionRule(
            name="hive_mind_daily",
            folder=root / "backups",
            pattern="hive_mind.20*-*-*.db",
            keep_last=7,
        ),
    ]


def run_audit(root: Path, args: argparse.Namespace) -> dict:
    tracked_dirs = [
        root / "backups",
        root / "config" / "component-lock-backups",
        root / "cerebro" / "thinking" / "session-logs",
        HOME / ".claude-mem" / "backups",
        HOME / ".swarmclaw" / "backups",
    ]
    directory_stats = {
        _repo_rel(path, root): _dir_stats(path)
        for path in tracked_dirs
    }

    stale_candidates: dict[str, list[str]] = {}
    for rule in _retention_rules(root, args):
        stale = _stale_for_rule(rule)
        stale_candidates[rule.name] = [str(path) for path in stale]

    legacy_stale = _legacy_snapshot_candidates(
        root,
        keep_per_family=args.keep_legacy_per_family,
        max_age_days=args.legacy_max_age_days,
    )
    stale_candidates["legacy_snapshot_dirs"] = [str(path) for path in legacy_stale]

    return {
        "root": str(root),
        "directory_stats": directory_stats,
        "secret_hits": _secret_hits(root),
        "stale_candidates": stale_candidates,
    }


def apply_prune(report: dict) -> list[str]:
    removed: list[str] = []
    for paths in report["stale_candidates"].values():
        for stale in paths:
            path = Path(stale)
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
                removed.append(stale)
                # Remove recovery manifest when pruning DB backups.
                if path.name.startswith("hive_mind.") and path.suffix == ".db":
                    path.with_suffix(".manifest.json").unlink(missing_ok=True)
    return removed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--keep-umc", type=int, default=10)
    parser.add_argument("--keep-component-lock", type=int, default=20)
    parser.add_argument("--keep-session-logs", type=int, default=10)
    parser.add_argument("--keep-fk-repair", type=int, default=5)
    parser.add_argument("--keep-legacy-per-family", type=int, default=1)
    parser.add_argument("--legacy-max-age-days", type=int, default=30)
    parser.add_argument("--apply", action="store_true", help="Actually remove stale files")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    return parser.parse_args()


def _human_summary(report: dict, removed: list[str] | None = None) -> str:
    lines = []
    lines.append("Backup Audit Summary")
    lines.append("====================")
    lines.append("")
    for rel, stats in report["directory_stats"].items():
        lines.append(
            f"- {rel}: exists={stats['exists']} files={stats['files']} bytes={stats['bytes']}"
        )
    lines.append("")
    lines.append(f"- Secret hits: {len(report['secret_hits'])}")
    lines.append(
        f"- Stale candidates: {sum(len(v) for v in report['stale_candidates'].values())}"
    )
    if removed is not None:
        lines.append(f"- Removed files: {len(removed)}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    report = run_audit(root, args)

    removed: list[str] | None = None
    if args.apply:
        removed = apply_prune(report)

    if args.json:
        payload = dict(report)
        if removed is not None:
            payload["removed"] = removed
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(_human_summary(report, removed=removed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
