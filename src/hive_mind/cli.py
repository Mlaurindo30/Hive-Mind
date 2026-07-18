"""Hive-Mind CLI entry point (F1).

Implements only:
  - ``hive-mind --version``
  - ``hive-mind --help``
  - ``hive-mind project-root`` (with ``--project-root`` override)

The F1 scope does not include install/update/service management. Those
land in F2 onwards.
"""
from __future__ import annotations

import argparse
import json
import sys

from hive_mind.project import EX_CONFIG, ProjectRootNotFound, add_cli_argument, resolve_project_root


def _get_version() -> str:
    """Return the installed package version.

    The single source of truth is ``pyproject.toml::project.version``,
    read at runtime via importlib.metadata. This guarantees
    ``hive-mind --version`` matches the wheel filename and the
    project release version (3.10.1).
    """
    try:
        from importlib.metadata import version
        return version("hive-mind")
    except Exception:
        import re
        from pathlib import Path
        for candidate in (Path.cwd(), Path(__file__).resolve().parents[3]):
            pyproject = candidate / "pyproject.toml"
            if pyproject.is_file():
                m = re.search(
                    r"^version\s*=\s*\"([^\"]+)\"",
                    pyproject.read_text(encoding="utf-8"),
                    re.M,
                )
                if m:
                    return m.group(1)
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hive-mind",
        description="Hive-Mind control plane CLI (F1 stub).",
    )
    p.add_argument("--version", action="store_true", help="print the CLI version and exit")
    sub = p.add_subparsers(dest="command")
    pr = sub.add_parser("project-root", help="print the resolved project root path")
    add_cli_argument(pr)

    projects = sub.add_parser("projects", help="inspect canonical project identity")
    project_commands = projects.add_subparsers(dest="projects_command")
    audit = project_commands.add_parser(
        "audit", help="inventory legacy project labels without changing data"
    )
    audit.add_argument(
        "--claude-mem-db",
        default=None,
        help="read-only claude-mem SQLite path",
    )
    audit.add_argument(
        "--hive-db",
        default=None,
        help="read-only Hive-Mind SQLite path",
    )
    audit.add_argument(
        "--vault-root",
        default=None,
        help="read-only Markdown vault root",
    )
    audit.add_argument(
        "--registry",
        default=None,
        help="canonical project alias registry",
    )
    audit.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return p


def main(argv: "list[str] | None" = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"hive-mind {_get_version()}")
        return 0
    if args.command == "project-root":
        try:
            root = resolve_project_root(cli_root=args.project_root)
        except ProjectRootNotFound as exc:
            print(str(exc), file=sys.stderr)
            return EX_CONFIG
        print(str(root))
        return 0
    if args.command == "projects" and args.projects_command == "audit":
        from core.projects.audit import (
            DEFAULT_REGISTRY_PATH,
            audit_projects,
            render_audit_table,
        )

        rows = audit_projects(
            claude_mem_db=args.claude_mem_db,
            hive_db=args.hive_db,
            vault_root=args.vault_root,
            registry_path=args.registry or DEFAULT_REGISTRY_PATH,
        )
        if args.json:
            print(json.dumps([row.to_dict() for row in rows], ensure_ascii=False, indent=2))
        else:
            print(render_audit_table(rows))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
