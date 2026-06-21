#!/usr/bin/env python3
"""Validate realtime capture sources against the installed machine state.

This is intentionally grounded in real files. Missing agents are reported as
SKIP, but if an agent has transcript/database sources and its parser returns no
sessions, the check fails.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "scripts" / "capture"
sys.path.insert(0, str(CAPTURE_DIR))

import capture_core as core  # noqa: E402
from capture_adapters import ADAPTERS  # noqa: E402


def _source_mtime(path: Path) -> float:
    return core._src_mtime(path)


def _worker_ok() -> bool:
    try:
        with urllib.request.urlopen(f"{core.BASE}/health", timeout=3) as response:
            return response.status == 200 and json.loads(response.read().decode()).get("status") == "ok"
    except Exception:
        return False


def _service_active(name: str) -> bool:
    try:
        return subprocess.run(
            ("systemctl", "--user", "is-active", "--quiet", name),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
    except Exception:
        return False


def _glob_existing(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        for raw in glob.glob(pattern):
            path = Path(raw)
            if path.exists():
                paths.append(path)
    return sorted(set(paths), key=lambda p: str(p))


def _session_counts(sessions: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "sessions": len(sessions),
        "prompts": sum(len(item.get("prompts") or []) for item in sessions),
        "turns": sum(len(item.get("turns") or []) for item in sessions),
    }


def _sqlite_has_any_rows(path: Path) -> bool | None:
    if path.suffix not in {".db", ".sqlite", ".sqlite3"}:
        return None
    try:
        import sqlite3

        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
        tables = [
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            if con.execute(f"SELECT 1 FROM {quoted} LIMIT 1").fetchone():
                con.close()
                return True
        con.close()
        return False
    except Exception:
        return None


def validate_platform(name: str, adapter: dict[str, Any], *, max_sources: int) -> dict[str, Any]:
    sources = [p for p in _glob_existing(adapter.get("sources", [])) if p.is_file()]
    watches = [p for p in _glob_existing(adapter.get("watch", [])) if p.is_dir()]
    installed = bool(sources or watches)
    result: dict[str, Any] = {
        "platform": name,
        "status": "SKIP",
        "installed": installed,
        "mode": adapter.get("mode"),
        "source_count": len(sources),
        "watch_count": len(watches),
        "checked_sources": [],
    }
    if not installed:
        result["reason"] = "no source/watch path found"
        return result
    if not sources:
        result["status"] = "WARN"
        result["reason"] = "watch path exists but no source file found yet"
        return result

    newest = sorted(sources, key=_source_mtime, reverse=True)[:max_sources]
    total_sessions = 0
    parser_errors: list[str] = []
    for source in newest:
        try:
            sessions = adapter["parser"](source)
            counts = _session_counts(sessions)
            total_sessions += counts["sessions"]
            result["checked_sources"].append(
                {
                    "path": str(source),
                    "mtime": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(_source_mtime(source))),
                    **counts,
                }
            )
        except Exception as exc:
            parser_errors.append(f"{source}: {exc}")

    if parser_errors:
        result["status"] = "FAIL"
        result["reason"] = "; ".join(parser_errors[:3])
    elif total_sessions <= 0:
        sqlite_states = [_sqlite_has_any_rows(source) for source in newest]
        if sqlite_states and all(state is False for state in sqlite_states):
            result["status"] = "WARN"
            result["reason"] = "sqlite source exists but has no rows yet"
        else:
            result["status"] = "FAIL"
            result["reason"] = "source files exist but parser returned zero sessions"
    else:
        result["status"] = "OK"
    return result


def run(max_sources: int) -> dict[str, Any]:
    platforms = [
        validate_platform(name, adapter, max_sources=max_sources)
        for name, adapter in sorted(ADAPTERS.items())
    ]
    failures = [item for item in platforms if item["status"] == "FAIL"]
    return {
        "worker": {"status": "OK" if _worker_ok() else "FAIL", "url": core.BASE},
        "capture_realtime": {
            "status": "OK" if _service_active("sinapse-capture-realtime.service") else "WARN",
            "service": "sinapse-capture-realtime.service",
        },
        "platforms": platforms,
        "healthy": not failures and _worker_ok(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate real capture sources and parsers.")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--max-sources", type=int, default=3)
    args = parser.parse_args(argv)

    report = run(max_sources=args.max_sources)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("Capture Sources Doctor")
        print(f"worker: {report['worker']['status']} ({report['worker']['url']})")
        print(
            "capture-realtime: "
            f"{report['capture_realtime']['status']} ({report['capture_realtime']['service']})"
        )
        for item in report["platforms"]:
            detail = item.get("reason") or f"{item['source_count']} source(s), {item['watch_count']} watch dir(s)"
            print(f"{item['status']:4} {item['platform']:14} {detail}")
            for checked in item.get("checked_sources", [])[:1]:
                print(
                    "     "
                    f"{checked['path']} | sessions={checked['sessions']} "
                    f"prompts={checked['prompts']} turns={checked['turns']}"
                )
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
