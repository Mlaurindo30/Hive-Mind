#!/usr/bin/env python3
"""Fail when distributable Hive-Mind artifacts disagree on the release version."""
from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path


def parse_core_version(path: Path) -> str:
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$', path.read_text(encoding="utf-8"), re.M)
    if not match:
        raise ValueError(f"missing __version__ in {path}")
    return match.group(1)


def release_versions(root: Path) -> dict[str, str]:
    with (root / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    package = json.loads((root / "npm" / "package.json").read_text(encoding="utf-8"))
    return {
        "pyproject.toml": pyproject["project"]["version"],
        "npm/package.json": package["version"],
        "core/version.py": parse_core_version(root / "core" / "version.py"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    versions = release_versions(args.source_root.resolve())
    distinct = sorted(set(versions.values()))
    if len(distinct) != 1:
        for source, version in versions.items():
            print(f"{source}: {version}")
        print("version contract failed: release artifacts disagree")
        return 1
    print(f"version contract OK: {distinct[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
