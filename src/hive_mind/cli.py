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
import os
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

    agents_cmd = sub.add_parser("agents", help="detect and manage agent integrations")
    agents_sub = agents_cmd.add_subparsers(dest="agents_command")
    ag_detect = agents_sub.add_parser("detect", help="detect installed agent providers")
    ag_detect.add_argument("--json", action="store_true", help="emit as JSON")
    ag_list = agents_sub.add_parser("list", help="list all supported providers")
    ag_list.add_argument("--json", action="store_true", help="emit as JSON")
    ag_reg = agents_sub.add_parser(
        "register",
        help="register the Hive-Mind MCP server with detected providers "
        "(inspection only unless --apply)",
    )
    ag_reg.add_argument(
        "--apply",
        action="store_true",
        help="actually write the provider configs (default: dry-run)",
    )
    ag_reg.add_argument("--only", default=None, help="register a single provider by id")
    ag_reg.add_argument("--project-root", default=None, help="project root override")
    ag_reg.add_argument("--json", action="store_true", help="emit as JSON")

    validate_cmd = sub.add_parser("validate", help="validate the pipeline against real data")
    validate_sub = validate_cmd.add_subparsers(dest="validate_command")
    val_agents = validate_sub.add_parser(
        "agents",
        help="multiagent capture canary over real sources and real delivery state",
    )
    val_agents.add_argument("--only", default=None, help="validate a single provider")
    val_agents.add_argument("--json", action="store_true", help="emit as JSON")

    backup_cmd = sub.add_parser("backup", help="verified SQLite backup workflow")
    backup_sub = backup_cmd.add_subparsers(dest="backup_command")
    bk_run = backup_sub.add_parser("run", help="create a verified backup")
    bk_run.add_argument("--apply", action="store_true",
                        help="actually write the backup (default: dry-run)")
    bk_run.add_argument("--json", action="store_true", help="emit as JSON")
    bk_status = backup_sub.add_parser("status", help="what backups exist right now")
    bk_status.add_argument("--json", action="store_true", help="emit as JSON")
    bk_verify = backup_sub.add_parser("verify", help="re-check a backup manifest")
    bk_verify.add_argument("--manifest", default=None, help="manifest path")
    bk_verify.add_argument("--json", action="store_true", help="emit as JSON")
    bk_restore = backup_sub.add_parser(
        "restore", help="restore into an alternate directory (never in place by default)"
    )
    bk_restore.add_argument("--manifest", required=True, help="manifest to restore from")
    bk_restore.add_argument("--into", required=True, help="destination directory")
    bk_restore.add_argument(
        "--overwrite-live", action="store_true",
        help="DESTRUCTIVE: replace existing files at the destination",
    )
    bk_restore.add_argument("--json", action="store_true", help="emit as JSON")
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
    if args.command == "agents":
        return _agents(args)
    if args.command == "validate" and args.validate_command == "agents":
        return _validate_agents(args)
    if args.command == "backup":
        return _backup(args)
    parser.print_help()
    return 0


def _backup(args) -> int:
    """Verified backup workflow. `run` is dry-run unless --apply."""
    from pathlib import Path

    from hive_mind.maintenance import backup as engine
    from hive_mind.maintenance.lock import MaintenanceLockError

    command = args.backup_command

    if command == "status":
        data = engine.status()
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        print(f"{'TARGET':<14} {'SRC':<5} {'BACKUPS':>7}  NEWEST")
        for entry in data["targets"]:
            src = "yes" if entry["source_present"] else "no"
            print(f"{entry['name']:<14} {src:<5} {entry['backups']:>7}  "
                  f"{entry['newest'] or '-'}")
        print("\ncoverage:")
        for component, state in data["coverage"].items():
            print(f"  {component:<20} {state}")
        return 0

    if command == "run":
        try:
            report = engine.run(dry_run=not args.apply)
        except MaintenanceLockError as exc:
            print(f"backup: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0 if report.healthy else 1
        mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
        print(f"hive-mind backup run — {mode}\n")
        for result in report.results:
            print(f"  {result.status:<5} {result.name:<14} {result.detail}")
            for pruned in result.pruned:
                print(f"        pruned: {pruned}")
        if report.manifest_path:
            print(f"\n  manifest: {report.manifest_path}")
        if not args.apply:
            print("\nRe-run with --apply to write the backup.")
        return 0 if report.healthy else 1

    if command == "verify":
        manifest = args.manifest
        if not manifest:
            for target in engine.default_targets():
                found = engine.latest_manifest(target.dest_dir)
                if found:
                    manifest = found
                    break
        if not manifest:
            print("no manifest found; run `hive-mind backup run --apply` first",
                  file=sys.stderr)
            return 1
        result = engine.verify(manifest)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"verify {result['manifest']}")
            for check in result["checks"]:
                mark = "OK  " if check["ok"] else "FAIL"
                print(f"  {mark} {check['name']:<14} {check['reason']}")
        return 0 if result["ok"] else 1

    if command == "restore":
        try:
            result = engine.restore(
                args.manifest, Path(args.into),
                allow_overwrite_live=args.overwrite_live,
            )
        except engine.RestoreRefused as exc:
            print(f"restore refused: {exc}", file=sys.stderr)
            return 1
        except (ValueError, FileNotFoundError) as exc:
            print(f"restore failed: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for entry in result["restored"]:
                print(f"  restored {entry['name']} -> {entry['path']}")
        return 0

    print("usage: hive-mind backup {run|status|verify|restore}", file=sys.stderr)
    return 1


def _validate_agents(args) -> int:
    """Real-data capture canary. Reads only; writes nothing."""
    from hive_mind.validation import canary

    report, outbox, umc = canary.run([args.only] if args.only else None)

    if args.json:
        print(json.dumps(
            {"report": report.to_dict(),
             "outbox": outbox.__dict__, "umc": umc.__dict__},
            ensure_ascii=False, indent=2, default=str,
        ))
        return 0 if report.ok else 1

    print("hive-mind validate agents — real sources, real parsers, read-only\n")
    for r in report.results:
        mark = {"PASSED": "OK  ", "FAILED": "FAIL", "SKIPPED": "--  ", "ERROR": "ERR "}[
            r.status.value
        ]
        detail = r.reason or f"project_id={r.project_id} sessions={r.inserted}"
        print(f"  {mark} {r.provider:<12} {detail}")

    print(f"\n  delivery state ({outbox.path}):")
    if not outbox.exists:
        print("    outbox absent")
    else:
        print(f"    {outbox.total} events, {outbox.delivered} delivered, "
              f"{outbox.undelivered} undelivered")
        if outbox.stalled:
            print("    *** NOTHING was ever delivered — the chain is broken ***")

    print(f"\n  UMC ({umc.path}):")
    if not umc.exists:
        print("    UMC absent")
    else:
        print(f"    {umc.observations} observations, "
              f"{umc.canonical} canonical workspace ({umc.canonical_pct:.1f}%), "
              f"{umc.legacy} legacy/default")

    print(f"\n  {len(report.passed)} passed, {len(report.failed)} failed "
          f"of {len(report.results)}")
    return 0 if report.ok else 1


def _agents(args) -> int:
    from hive_mind.agents.detect import detect_providers
    from hive_mind.agents.registry import PROVIDERS

    if args.agents_command == "list":
        rows = [{"id": p.id, "name": p.name} for p in PROVIDERS]
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for p in PROVIDERS:
                print(f"{p.id:<12} {p.name}")
        return 0

    if args.agents_command == "detect":
        results = detect_providers()
        if args.json:
            print(json.dumps(
                [{"id": r.id, "name": r.name, "detected": r.detected,
                  "evidence": r.evidence} for r in results],
                ensure_ascii=False, indent=2,
            ))
        else:
            found = [r for r in results if r.detected]
            for r in results:
                mark = "OK " if r.detected else "-- "
                extra = f"  ({r.evidence})" if r.evidence else ""
                print(f"{mark}{r.id:<12} {r.name}{extra}")
            print(f"\n{len(found)} of {len(results)} providers detected")
        return 0

    if args.agents_command == "register":
        return _agents_register(args)

    print("usage: hive-mind agents {detect|list|register}", file=sys.stderr)
    return 1


def _agents_register(args) -> int:
    """Register the MCP server with detected providers. Dry-run unless --apply."""
    import sys as _sys
    from pathlib import Path

    from hive_mind.agents.detect import detect_providers
    from hive_mind.agents.register import register_providers

    try:
        root = resolve_project_root(cli_root=args.project_root)
    except ProjectRootNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EX_CONFIG

    if args.only:
        targets = [args.only]
    else:
        targets = [r.id for r in detect_providers() if r.detected]
    if not targets:
        print("no providers detected", file=sys.stderr)
        return 1

    home = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
    appdata = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
    server = str(root / "scripts" / "services" / "sinapse_mcp.py")

    try:
        results = register_providers(
            targets,
            home=home,
            appdata=appdata,
            project_root=root,
            python=_sys.executable,
            server=server,
            dry_run=not args.apply,
        )
    except KeyError as exc:
        print(f"unknown provider: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2))
        return 0

    mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
    print(f"hive-mind agents register — {mode}\n")
    for r in results:
        if not r.supported:
            print(f"  SKIP  {r.provider:<10} {r.path}\n        {r.note}")
            continue
        state = "would change" if not args.apply and r.changed else (
            "changed" if r.changed else "already current"
        )
        print(f"  {'OK ' if r.changed else '== '}  {r.provider:<10} {r.path}  [{state}]")
    if not args.apply:
        print("\nRe-run with --apply to write these configs.")
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
