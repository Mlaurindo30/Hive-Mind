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

    config_cmd = sub.add_parser("config", help="manage runtime declarative manifest")
    config_sub = config_cmd.add_subparsers(dest="config_command")
    cfg_val = config_sub.add_parser("validate", help="validate config/runtime.yaml manifest")
    cfg_val.add_argument("--manifest", default=None, help="path to runtime.yaml manifest")
    cfg_show = config_sub.add_parser("show", help="show parsed config/runtime.yaml manifest")
    cfg_show.add_argument("--manifest", default=None, help="path to runtime.yaml manifest")
    cfg_show.add_argument("--json", action="store_true", help="emit as JSON")

    service_cmd = sub.add_parser("service", help="inspect daemon-observed services")
    service_sub = service_cmd.add_subparsers(dest="service_command")
    svc_status = service_sub.add_parser(
        "status", help="show the daemon's shadow observation of services"
    )
    svc_status.add_argument("--state-dir", default=None, help="daemon state directory")
    svc_status.add_argument("--project-root", default=None, help="project root override")
    svc_status.add_argument("--json", action="store_true", help="emit as JSON")
    svc_ping = service_sub.add_parser(
        "ping", help="check the daemon control socket is alive"
    )
    svc_ping.add_argument("--state-dir", default=None, help="daemon state directory")
    svc_ping.add_argument("--project-root", default=None, help="project root override")
    return p


def _state_dir_from(args):
    from pathlib import Path

    if args.state_dir:
        return Path(args.state_dir)
    root = resolve_project_root(cli_root=args.project_root)
    return root / ".hive-mind" / "state"


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
    if args.command == "config":
        from pathlib import Path
        from hive_mind.daemon.manifest import load_manifest, validate_manifest
        manifest_p = Path(args.manifest) if args.manifest else Path("config/runtime.yaml")

        if args.config_command == "validate":
            errors = validate_manifest(manifest_p)
            if errors:
                for err in errors:
                    print(err, file=sys.stderr)
                return 1
            print("Manifesto válido.")
            return 0

        if args.config_command == "show":
            try:
                manifest_obj = load_manifest(manifest_p)
            except Exception as exc:
                print(str(exc), file=sys.stderr)
                return 1

            if args.json:
                print(manifest_obj.model_dump_json(indent=2))
            else:
                import yaml
                print(yaml.safe_dump(manifest_obj.model_dump(), allow_unicode=True, default_flow_style=False))
            return 0
    if args.command == "service" and args.service_command == "status":
        return _service_status(args)
    if args.command == "service" and args.service_command == "ping":
        return _service_ping(args)
    parser.print_help()
    return 0


def _service_ping(args) -> int:
    """Ping the daemon control socket. Non-zero if it is not reachable."""
    from hive_mind.daemon.control import ControlClient, ControlRequest

    try:
        state_dir = _state_dir_from(args)
    except ProjectRootNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EX_CONFIG
    try:
        resp = ControlClient(state_dir=state_dir).request(
            ControlRequest(command="ping"), timeout=3.0
        )
    except ConnectionError as exc:
        print(f"control socket unreachable: {exc}", file=sys.stderr)
        return 1
    if resp.ok:
        print("pong")
        return 0
    print(f"control socket error: {resp.error}", file=sys.stderr)
    return 1


def _service_status(args) -> int:
    """Read-only view of the daemon's shadow observation. Mutates nothing."""
    from pathlib import Path

    if args.state_dir:
        state_dir = Path(args.state_dir)
    else:
        try:
            root = resolve_project_root(cli_root=args.project_root)
        except ProjectRootNotFound as exc:
            print(str(exc), file=sys.stderr)
            return EX_CONFIG
        state_dir = root / ".hive-mind" / "state"

    state_file = state_dir / "services.shadow.json"
    if not state_file.exists():
        print(
            f"no shadow observation found at {state_file}; "
            "run `hive-mindd run --shadow` first",
            file=sys.stderr,
        )
        return 1
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read shadow state: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    ready = "ready" if state.get("ready") else "NOT-ready"
    print(
        f"mode={state.get('mode')} profile={state.get('profile')} "
        f"required={ready}"
    )
    print(f"{'SERVICE':<28} {'OWNERSHIP':<9} {'REQ':<4} {'READINESS':<10} ORDER")
    for svc in state.get("services", []):
        print(
            f"{svc.get('name', ''):<28} {svc.get('ownership', ''):<9} "
            f"{'yes' if svc.get('required') else 'no':<4} "
            f"{svc.get('readiness', ''):<10} {svc.get('startup_order', '')}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
