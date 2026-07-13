#!/usr/bin/env python3
"""Fail when distributable Hive-Mind artifacts disagree or regress below a release floor."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from pathlib import Path

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_core_version(path: Path) -> str:
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$', path.read_text(encoding="utf-8"), re.M)
    if not match:
        raise ValueError(f"missing __version__ in {path}")
    return match.group(1)


def parse_version_literal(path: Path, pattern: str, label: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.M)
    if not match:
        raise ValueError(f"missing release version in {label}")
    return match.group(1)


def parse_changelog_version(path: Path) -> str:
    return parse_version_literal(path, r"^## Unreleased.*?v(\d+\.\d+\.\d+)", str(path))


def release_versions(root: Path) -> dict[str, str]:
    with (root / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    package = json.loads((root / "npm" / "package.json").read_text(encoding="utf-8"))
    return {
        "pyproject.toml": pyproject["project"]["version"],
        "npm/package.json": package["version"],
        "core/version.py": parse_core_version(root / "core" / "version.py"),
        "scripts/services/sinapse-api.py": parse_version_literal(
            root / "scripts" / "services" / "sinapse-api.py",
            r'^\s*version="(\d+\.\d+\.\d+)"',
            "sinapse-api",
        ),
        "scripts/services/sinapse_mcp.py": parse_version_literal(
            root / "scripts" / "services" / "sinapse_mcp.py",
            r'"serverInfo": \{"name": "sinapse-memory", "version": "(\d+\.\d+\.\d+)"\}',
            "sinapse-mcp",
        ),
        "core/telemetry.py": parse_version_literal(
            root / "core" / "telemetry.py",
            r'"service\.version": "(\d+\.\d+\.\d+)"',
            "telemetry",
        ),
        "CHANGELOG.md": parse_changelog_version(root / "CHANGELOG.md"),
    }


def parse_semver(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value.lstrip("v"))
    if not match:
        raise ValueError(f"unsupported release version: {value}")
    return tuple(int(part) for part in match.groups())


def validate_versions(versions: dict[str, str], minimum_version: str | None = None) -> list[str]:
    distinct = sorted(set(versions.values()))
    if len(distinct) != 1:
        return ["release artifacts disagree"]
    version = distinct[0]
    errors = []
    if minimum_version and parse_semver(version) < parse_semver(minimum_version):
        errors.append(f"release version {version} is below minimum {minimum_version}")
    return errors


def latest_git_tag(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip().lstrip("v") if result.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--minimum-version")
    args = parser.parse_args()
    root = args.source_root.resolve()
    versions = release_versions(root)
    minimum_version = args.minimum_version or latest_git_tag(root)
    errors = validate_versions(versions, minimum_version)
    if errors:
        for source, version in versions.items():
            print(f"{source}: {version}")
        for error in errors:
            print(f"version contract failed: {error}")
        return 1
    print(f"version contract OK: {next(iter(versions.values()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())