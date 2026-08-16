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
    migrate_legacy = project_commands.add_parser(
        "migrate-legacy",
        help="controlled migration of legacy UMC rows with dry-run by default",
    )
    migrate_legacy.add_argument(
        "--claude-mem-db",
        default=None,
        help="Claude Mem SQLite path used to recover preserved session labels",
    )
    migrate_legacy.add_argument(
        "--hive-db",
        default=None,
        help="Hive-Mind SQLite path to inspect or mutate",
    )
    migrate_legacy.add_argument(
        "--registry",
        default=None,
        help="canonical project alias registry",
    )
    migrate_legacy.add_argument(
        "--source-workspace",
        default="unclassified/legacy",
        help="legacy workspace bucket to inspect (default: unclassified/legacy)",
    )
    migrate_legacy.add_argument(
        "--target-project",
        default=None,
        help="restrict apply/dry-run to a single canonical project_id",
    )
    migrate_legacy.add_argument(
        "--apply",
        action="store_true",
        help="actually rewrite matching rows (default: dry-run only)",
    )
    migrate_legacy.add_argument("--json", action="store_true", help="emit machine-readable JSON")

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
        "status", help="show the daemon state for observed or managed services"
    )
    svc_status.add_argument("--state-dir", default=None, help="daemon state directory")
    svc_status.add_argument("--project-root", default=None, help="project root override")
    svc_status.add_argument("--json", action="store_true", help="emit as JSON")
    svc_ping = service_sub.add_parser(
        "ping", help="check the daemon control socket is alive"
    )
    svc_ping.add_argument("--state-dir", default=None, help="daemon state directory")
    svc_ping.add_argument("--project-root", default=None, help="project root override")
    svc_windows_jobs = service_sub.add_parser(
        "windows-jobs", help="register Windows scheduled knowledge jobs"
    )
    svc_windows_jobs.add_argument("--project-root", default=None, help="project root override")
    svc_windows_jobs.add_argument("--backup-dir", default=None, help="directory for exported task XML backups")
    svc_windows_jobs.add_argument("--apply", action="store_true", help="actually write the scheduled tasks")
    svc_windows_jobs.add_argument("--json", action="store_true", help="emit as JSON")
    svc_windows_runtime = service_sub.add_parser(
        "windows-runtime", help="register Windows autostart/runtime tasks"
    )
    svc_windows_runtime.add_argument("--project-root", default=None, help="project root override")
    svc_windows_runtime.add_argument("--apply", action="store_true", help="actually write the runtime tasks")
    svc_windows_runtime.add_argument("--json", action="store_true", help="emit as JSON")
    svc_manifest = service_sub.add_parser(
        "manifest", help="emit the native runtime service manifest"
    )
    svc_manifest.add_argument("--project-root", default=None, help="project root override")
    svc_manifest.add_argument("--json", action="store_true", help="emit as JSON")

    doctor_cmd = sub.add_parser("doctor", help="diagnose agent integrations (read-only)")
    doctor_cmd.add_argument("--only", "--self", "--agent", dest="only", default=None,
                            help="diagnose a single provider by id")
    doctor_cmd.add_argument("--project-root", default=None, help="project root override")
    doctor_cmd.add_argument("--json", action="store_true", help="emit as JSON")

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
    ag_reg.add_argument("--only", "--self", "--agent", dest="only", default=None,
                        help="register a single provider by id")
    ag_reg.add_argument("provider", nargs="?", default=None,
                        help="the same, given positionally (legacy spelling)")
    ag_reg.add_argument("--project-root", default=None, help="project root override")
    ag_reg.add_argument("--json", action="store_true", help="emit as JSON")
    ag_reg.add_argument(
        "--instructions", action="store_true",
        help="also install the managed instruction block for each provider",
    )
    # Compatibility with the registrar scripts D009-R6 reduced to wrappers.
    # See hive_mind/agents/compat.py for why these live here and not there.
    ag_reg.add_argument("--no-instructions", dest="no_instructions",
                        action="store_true",
                        help="never touch prompt files (legacy flag)")
    ag_reg.add_argument("--check", action="store_true",
                        help="diagnose only; write nothing (legacy flag)")
    ag_reg.add_argument("--list", action="store_true",
                        help="print the valid agent keys and exit (legacy flag)")
    ag_reg.add_argument("--codex-only", dest="codex_only", action="store_true",
                        help="shorthand for --only codex (legacy flag)")
    ag_reg.add_argument("--claude-only", dest="claude_only", action="store_true",
                        help="shorthand for --only claude (legacy flag)")
    ag_doc = agents_sub.add_parser("doctor", help="diagnose agent integrations (read-only)")
    ag_doc.add_argument("--only", "--self", "--agent", dest="only", default=None,
                        help="diagnose a single provider by id")
    ag_doc.add_argument("--project-root", default=None, help="project root override")
    ag_doc.add_argument("--json", action="store_true", help="emit as JSON")
    ag_unreg = agents_sub.add_parser(
        "unregister", help="remove the Hive-Mind entry from provider configs"
    )
    ag_unreg.add_argument("--apply", action="store_true", help="actually write (default: dry-run)")
    ag_unreg.add_argument("--only", default=None, help="a single provider by id")
    ag_unreg.add_argument("--project-root", default=None, help="project root override")
    ag_unreg.add_argument(
        "--instructions", action="store_true", help="also remove the instruction block"
    )
    ag_unreg.add_argument("--json", action="store_true", help="emit as JSON")

    validate_cmd = sub.add_parser("validate", help="validate the pipeline against real data")
    validate_sub = validate_cmd.add_subparsers(dest="validate_command")
    val_agents = validate_sub.add_parser(
        "agents",
        help="multiagent capture canary over real sources and real delivery state",
    )
    val_agents.add_argument(
        "--only", action="append", default=None,
        help="validate an explicit provider (repeatable)",
    )
    val_agents.add_argument(
        "--marker", default=None,
        help="fresh marker already emitted by the provider (does not run it)",
    )
    val_agents.add_argument(
        "--since", type=int, default=None, metavar="EPOCH",
        help="minimum Unix epoch for --marker evidence",
    )
    val_agents.add_argument("--json", action="store_true", help="emit as JSON")
    val_delivery = validate_sub.add_parser(
        "delivery",
        help="inspect legacy UMC buckets and historical capture backlog (read-only)",
    )
    val_delivery.add_argument("--outbox-db", default=None, help="read-only capture outbox SQLite path")
    val_delivery.add_argument("--hive-db", default=None, help="read-only Hive-Mind SQLite path")
    val_delivery.add_argument("--json", action="store_true", help="emit as JSON")
    val_topology = validate_sub.add_parser(
        "topology",
        help="inventory worktrees/copies and suggest safe cleanup disposition (read-only)",
    )
    val_topology.add_argument("--project-root", default=None, help="project root override")
    val_topology.add_argument("--json", action="store_true", help="emit as JSON")
    val_vault = validate_sub.add_parser(
        "vault",
        help="audit Markdown/link/encoding state of the vault (read-only)",
    )
    val_vault.add_argument("--vault-root", default=None, help="vault root override")
    val_vault.add_argument("--json", action="store_true", help="emit as JSON")

    vault_cmd = sub.add_parser("vault", help="controlled vault maintenance")
    vault_sub = vault_cmd.add_subparsers(dest="vault_command")
    vault_repair = vault_sub.add_parser(
        "repair-frontmatter",
        help="repair legacy invalid YAML frontmatter in vault notes (dry-run by default)",
    )
    vault_repair.add_argument("--vault-root", default=None, help="vault root override")
    vault_repair.add_argument("--apply", action="store_true", help="actually rewrite candidate notes")
    vault_repair.add_argument("--json", action="store_true", help="emit as JSON")
    vault_project_id = vault_sub.add_parser(
        "repair-project-id",
        help="repair missing project_id in legacy temporal neurons (dry-run by default)",
    )
    vault_project_id.add_argument("--vault-root", default=None, help="vault root override")
    vault_project_id.add_argument("--apply", action="store_true", help="actually rewrite candidate notes")
    vault_project_id.add_argument("--json", action="store_true", help="emit as JSON")
    vault_encoding = vault_sub.add_parser(
        "repair-encoding",
        help="repair legacy cp1252 bytes preserved in Markdown notes (dry-run by default)",
    )
    vault_encoding.add_argument("--vault-root", default=None, help="vault root override")
    vault_encoding.add_argument("--apply", action="store_true", help="actually rewrite candidate notes")
    vault_encoding.add_argument("--json", action="store_true", help="emit as JSON")

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
    bk_outbox = backup_sub.add_parser(
        "archive-historical-outbox",
        help="archive inert historical capture_outbox rows with dry-run by default",
    )
    bk_outbox.add_argument("--outbox-db", default=None, help="capture outbox SQLite path")
    bk_outbox.add_argument(
        "--cutoff-occurred-at",
        default=None,
        help="archive only rows with occurred_at <= this ISO timestamp",
    )
    bk_outbox.add_argument("--apply", action="store_true", help="actually archive rows")
    bk_outbox.add_argument("--json", action="store_true", help="emit as JSON")
    bk_scrub_outbox = backup_sub.add_parser(
        "scrub-capture-outbox",
        help="redact secret-shaped material from the legacy capture outbox (dry-run by default)",
    )
    bk_scrub_outbox.add_argument("--outbox-db", default=None, help="capture outbox SQLite path")
    bk_scrub_outbox.add_argument("--apply", action="store_true", help="actually rewrite candidate rows")
    bk_scrub_outbox.add_argument("--json", action="store_true", help="emit as JSON")
    bk_scrub_artifacts = backup_sub.add_parser(
        "scrub-runtime-artifacts",
        help="redact secret-shaped material from runtime log/audit artifacts (dry-run by default)",
    )
    bk_scrub_artifacts.add_argument("--project-root", default=None, help="project root override")
    bk_scrub_artifacts.add_argument("--apply", action="store_true", help="actually rewrite candidate files")
    bk_scrub_artifacts.add_argument("--json", action="store_true", help="emit as JSON")
    bk_scrub_env = backup_sub.add_parser(
        "scrub-env-backups",
        help="redact secret values from legacy .env files stored under backups/ (dry-run by default)",
    )
    bk_scrub_env.add_argument("--project-root", default=None, help="project root override")
    bk_scrub_env.add_argument("--apply", action="store_true", help="actually rewrite candidate files")
    bk_scrub_env.add_argument("--json", action="store_true", help="emit as JSON")
    bk_cleanup_topology = backup_sub.add_parser(
        "cleanup-topology-stale",
        help="archive and remove stale topology residues marked REMOVE_AFTER_APPROVAL",
    )
    bk_cleanup_topology.add_argument("--project-root", default=None, help="project root override")
    bk_cleanup_topology.add_argument("--archive-root", default=None, help="archive root override")
    bk_cleanup_topology.add_argument("--apply", action="store_true", help="actually archive/remove eligible stale targets")
    bk_cleanup_topology.add_argument("--json", action="store_true", help="emit as JSON")
    bk_topology = backup_sub.add_parser(
        "archive-topology",
        help="archive legacy topology paths classified as ARCHIVE (dry-run by default)",
    )
    bk_topology.add_argument("--project-root", default=None, help="project root override")
    bk_topology.add_argument("--archive-root", default=None, help="archive root override")
    bk_topology.add_argument("--apply", action="store_true", help="actually archive and remove eligible sources")
    bk_topology.add_argument("--json", action="store_true", help="emit as JSON")

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
    if args.command == "doctor":
        return _agents_doctor(args)
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
    if args.command == "projects" and args.projects_command == "migrate-legacy":
        from pathlib import Path
        from hive_mind.maintenance.legacy_migration import migrate_legacy_observations
        from hive_mind.projects.identity import DEFAULT_REGISTRY_PATH

        home = Path.home()
        root = Path(os.environ.get("SINAPSE_HOME", Path.cwd()))
        report = migrate_legacy_observations(
            claude_mem_db=args.claude_mem_db or home / ".claude-mem" / "claude-mem.db",
            hive_db=args.hive_db or root / "hive_mind.db",
            registry_path=args.registry or DEFAULT_REGISTRY_PATH,
            source_workspace=args.source_workspace,
            target_project_id=args.target_project,
            apply=args.apply,
        )
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            print("hive-mind projects migrate-legacy\n")
            print(f"  hive_db={report.hive_db}")
            print(f"  claude_mem_db={report.claude_mem_db}")
            print(f"  registry={report.registry_path}")
            print(f"  source_workspace={report.source_workspace}")
            print(f"  apply={report.apply} target_project={report.target_project_id or '-'}")
            print(
                f"  scanned={report.scanned} candidates={report.candidates} updated={report.updated}"
            )
            print(
                "  skipped:"
                f" missing_source_session={report.skipped_missing_source_session}"
                f" missing_sdk_session={report.skipped_missing_sdk_session}"
                f" missing_project_label={report.skipped_missing_project_label}"
                f" target_filter={report.skipped_target_filter}"
            )
            if report.candidate_rows_by_project:
                print("  candidate_rows_by_project:")
                for project, count in report.candidate_rows_by_project:
                    print(f"    - {project}: {count}")
            if report.unmapped_rows_by_label:
                print("  unmapped_rows_by_label:")
                for label, count in report.unmapped_rows_by_label:
                    print(f"    - {label}: {count}")
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
    if args.command == "service" and args.service_command == "windows-jobs":
        return _service_windows_jobs(args)
    if args.command == "service" and args.service_command == "windows-runtime":
        return _service_windows_runtime(args)
    if args.command == "service" and args.service_command == "manifest":
        return _service_manifest(args)
    if args.command == "agents":
        return _agents(args)
    if args.command == "validate" and args.validate_command == "agents":
        return _validate_agents(args)
    if args.command == "validate" and args.validate_command == "delivery":
        return _validate_delivery(args)
    if args.command == "validate" and args.validate_command == "topology":
        return _validate_topology(args)
    if args.command == "validate" and args.validate_command == "vault":
        return _validate_vault(args)
    if args.command == "vault":
        return _vault(args)
    if args.command == "backup":
        return _backup(args)
    parser.print_help()
    return 0


def _backup(args) -> int:
    """Verified backup workflow. `run` is dry-run unless --apply."""
    from pathlib import Path

    from hive_mind.maintenance import backup as engine
    from hive_mind.maintenance.historical_outbox import archive_historical_outbox
    from hive_mind.maintenance.lock import MaintenanceLockError
    from hive_mind.maintenance.scrub_capture_outbox import scrub_capture_outbox
    from hive_mind.maintenance.scrub_env_backups import scrub_env_backups
    from hive_mind.maintenance.scrub_runtime_artifacts import scrub_runtime_artifacts
    from hive_mind.maintenance.topology_archive import archive_topology, cleanup_topology_stale

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

    if command == "archive-historical-outbox":
        home = Path.home()
        report = archive_historical_outbox(
            outbox_db=args.outbox_db or home / ".claude-mem" / "capture.db",
            cutoff_occurred_at=args.cutoff_occurred_at,
            apply=args.apply,
        )
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0
        mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
        print(f"hive-mind backup archive-historical-outbox — {mode}\n")
        print(f"  outbox_db={report.outbox_db}")
        print(f"  cutoff_occurred_at={report.cutoff_occurred_at or '-'}")
        print(f"  scanned={report.scanned} eligible={report.eligible} archived={report.archived}")
        print(
            f"  blocked_attempted={report.blocked_attempted} "
            f"blocked_delivered={report.blocked_delivered} "
            f"blocked_dead_letter={report.blocked_dead_letter} "
            f"blocked_recent={report.blocked_recent}"
        )
        print(f"  oldest_eligible={report.oldest_eligible or '-'}")
        print(f"  newest_eligible={report.newest_eligible or '-'}")
        if report.providers:
            print("  providers:")
            for provider, count in report.providers:
                print(f"    - {provider}: {count}")
        return 0

    if command == "scrub-capture-outbox":
        report = scrub_capture_outbox(
            outbox_db=args.outbox_db or resolve_project_root() / "logs" / "capture-outbox.db",
            apply=args.apply,
        )
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0
        mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
        print(f"hive-mind backup scrub-capture-outbox — {mode}\n")
        print(f"  outbox_db={report.outbox_db}")
        print(f"  scanned_rows={report.scanned_rows}")
        print(f"  changed_rows={report.changed_rows}")
        print(f"  changed_payload_rows={report.changed_payload_rows}")
        print(f"  changed_error_rows={report.changed_error_rows}")
        print(f"  archive_rows={report.archive_rows}")
        return 0

    if command == "scrub-runtime-artifacts":
        root = resolve_project_root(cli_root=args.project_root)
        report = scrub_runtime_artifacts(project_root=root, apply=args.apply)
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0
        mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
        print(f"hive-mind backup scrub-runtime-artifacts — {mode}\n")
        print(f"  scanned={report.scanned}")
        print(f"  changed={report.changed}")
        for entry in report.entries:
            print(f"  - {'CHANGED' if entry.changed else 'OK'} {entry.path}")
        return 0

    if command == "scrub-env-backups":
        root = resolve_project_root(cli_root=args.project_root)
        report = scrub_env_backups(project_root=root, apply=args.apply)
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0
        mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
        print(f"hive-mind backup scrub-env-backups — {mode}\n")
        print(f"  scanned={report.scanned}")
        print(f"  changed={report.changed}")
        for entry in report.entries:
            suffix = f" redacted={','.join(entry.redacted_keys)}" if entry.redacted_keys else ""
            print(f"  - {'CHANGED' if entry.changed else 'OK'} {entry.path}{suffix}")
        return 0

    if command == "archive-topology":
        root = resolve_project_root(cli_root=args.project_root)
        report = archive_topology(
            project_root=root,
            archive_root=args.archive_root,
            apply=args.apply,
        )
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0
        mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
        print(f"hive-mind backup archive-topology — {mode}\n")
        print(f"  project_root={report.project_root}")
        print(f"  archive_root={report.archive_root}")
        print(f"  batch_dir={report.batch_dir}")
        print(f"  scanned={report.scanned} eligible={report.eligible} archived={report.archived} "
              f"removed={report.removed} preserved={report.preserved} skipped={report.skipped}")
        for entry in report.entries[:20]:
            print(f"  - {entry.status}: {entry.source_path} -> {entry.destination_path or '-'}")
            print(f"    action={entry.action} reason={entry.reason}")
        return 0

    if command == "cleanup-topology-stale":
        root = resolve_project_root(cli_root=args.project_root)
        report = cleanup_topology_stale(
            project_root=root,
            archive_root=args.archive_root,
            apply=args.apply,
        )
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0
        mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
        print(f"hive-mind backup cleanup-topology-stale — {mode}\n")
        print(f"  project_root={report.project_root}")
        print(f"  archive_root={report.archive_root}")
        print(f"  batch_dir={report.batch_dir}")
        print(f"  scanned={report.scanned} eligible={report.eligible} archived={report.archived} "
              f"removed={report.removed} preserved={report.preserved} skipped={report.skipped}")
        for entry in report.entries[:20]:
            print(f"  - {entry.status}: {entry.source_path} -> {entry.destination_path or '-'}")
            print(f"    action={entry.action} reason={entry.reason}")
        return 0

    print("usage: hive-mind backup {run|status|verify|restore|archive-historical-outbox|archive-topology|cleanup-topology-stale}", file=sys.stderr)
    return 1


def _validate_agents(args) -> int:
    """Real-data capture canary. Reads only; writes nothing."""
    from hive_mind.validation import canary

    marker_mode = args.marker is not None or args.since is not None
    if marker_mode:
        if args.marker is None or args.since is None or not args.only:
            print(
                "--marker requires --since and at least one --only provider",
                file=sys.stderr,
            )
            return 2
        report = canary.run_fresh_marker(
            marker=args.marker, since_epoch=args.since, providers=args.only
        )
        if args.json:
            print(json.dumps(
                {"marker": args.marker, "since_epoch": args.since,
                 "report": report.to_dict()},
                ensure_ascii=False, indent=2, default=str,
            ))
            return 0 if report.ok else 1
        print("hive-mind validate agents — fresh marker chain, read-only\n")
        for result in report.results:
            mark = {"PASSED": "OK  ", "FAILED": "FAIL", "SKIPPED": "--  ",
                    "ERROR": "ERR "}[result.status.value]
            detail = result.reason or f"workspace_id={result.project_id}"
            print(f"  {mark} {result.provider:<12} {detail}")
        print(f"\n  {len(report.passed)} passed, {len(report.failed)} failed "
              f"of {len(report.results)}")
        return 0 if report.ok else 1

    report, outbox, umc = canary.run(args.only)

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


def _validate_delivery(args) -> int:
    """Read-only delivery/legacy audit for safe cleanup planning."""
    from pathlib import Path

    from hive_mind.validation.delivery import (
        inspect_legacy_recovery,
        inspect_outbox,
        inspect_umc,
        inspect_umc_legacy,
    )

    home = Path.home()
    root = Path(os.environ.get("SINAPSE_HOME", Path.cwd()))
    outbox_path = Path(args.outbox_db) if args.outbox_db else home / ".claude-mem" / "capture.db"
    hive_path = Path(args.hive_db) if args.hive_db else root / "hive_mind.db"
    outbox = inspect_outbox(outbox_path)
    umc = inspect_umc(hive_path)
    legacy = inspect_umc_legacy(hive_path)
    recovery = inspect_legacy_recovery(hive_path)

    if args.json:
        print(json.dumps(
            {
                "outbox": outbox.__dict__,
                "umc": umc.__dict__,
                "legacy": legacy.__dict__,
                "recovery": recovery.__dict__,
            },
            ensure_ascii=False, indent=2, default=str,
        ))
        return 0

    print("hive-mind validate delivery — read-only\n")
    print(f"  outbox: {outbox.path}")
    print(f"    total={outbox.total} delivered={outbox.delivered} "
          f"undelivered={outbox.undelivered} dead_letter={outbox.dead_letter}")
    print(f"    oldest_undelivered={outbox.oldest_undelivered or '-'}")
    print(f"    newest_undelivered={outbox.newest_undelivered or '-'}")
    if outbox.by_provider:
        print("    by_provider:")
        for provider, count in outbox.by_provider:
            print(f"      - {provider}: {count}")

    print(f"\n  umc: {umc.path}")
    print(f"    observations={umc.observations} canonical={umc.canonical} "
          f"legacy/default={umc.legacy}")
    print(f"    default_workspace={legacy.default_workspace} empty_workspace={legacy.empty_workspace}")
    print(f"    unclassified_legacy={legacy.unclassified_legacy} archived_quarantine={legacy.archived_quarantine}")
    if legacy.default_active_by_project:
        print("    default_active_by_project:")
        for project, count in legacy.default_active_by_project[:10]:
            print(f"      - {project}: {count}")
    if legacy.unclassified_active_by_project:
        print("    unclassified_active_by_project:")
        for project, count in legacy.unclassified_active_by_project[:10]:
            print(f"      - {project}: {count}")
    print(f"\n  recovery: {recovery.path}")
    print(f"    legacy_source_sessions={recovery.legacy_source_sessions} decisions_found={recovery.decisions_found} "
          f"bridged_recoverable={recovery.bridged_recoverable}")
    if recovery.bridged_by_project:
        print("    bridged_by_project:")
        for project, count in recovery.bridged_by_project[:10]:
            print(f"      - {project}: {count}")
    print(f"    claude_mem_db={recovery.claude_mem_path or '-'} exists={recovery.claude_mem_exists}")
    print(f"    session_rows_found={recovery.session_rows_found} "
          f"session_project_signals={recovery.session_project_signals} "
          f"canonical_alias_matches={recovery.canonical_alias_matches}")
    if recovery.canonical_signal_by_project:
        print("    canonical_signal_by_project:")
        for project, count in recovery.canonical_signal_by_project[:10]:
            print(f"      - {project}: {count}")
    if recovery.unmapped_session_projects:
        print("    unmapped_session_projects:")
        for project, count in recovery.unmapped_session_projects[:10]:
            print(f"      - {project}: {count}")
    return 0


def _validate_topology(args) -> int:
    from hive_mind.validation.topology import inventory_topology

    try:
        root = resolve_project_root(cli_root=args.project_root)
    except ProjectRootNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EX_CONFIG
    entries = inventory_topology(root)
    if args.json:
        print(json.dumps([entry.to_dict() for entry in entries], ensure_ascii=False, indent=2))
        return 0

    print("hive-mind validate topology — read-only\n")
    for entry in entries:
        print(
            f"  {entry.classification:<18} {entry.disposition:<21} "
            f"exists={str(entry.exists).lower():<5} dirty={entry.dirty_lines if entry.dirty_lines is not None else '-':<4} "
            f"{entry.path}"
        )
        if entry.branch or entry.head:
            print(f"    branch={entry.branch or '-'} head={entry.head or '-'}")
        print(f"    reason={entry.reason}")
    return 0


def _validate_vault(args) -> int:
    from pathlib import Path

    from hive_mind.validation.vault import audit_vault_markdown

    root = Path(args.vault_root) if args.vault_root else Path(os.environ.get("SINAPSE_HOME", Path.cwd())) / "cerebro"
    report = audit_vault_markdown(root)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print("hive-mind validate vault — read-only\n")
    metrics = report.metrics
    print(f"  vault: {report.vault_root}")
    print(f"    total_md={metrics.total_md} empty_md={metrics.empty_md} invalid_frontmatter={metrics.invalid_frontmatter}")
    print(f"    missing_project_id={metrics.missing_project_id} mojibake_files={metrics.mojibake_files}")
    print(f"    broken_wikilinks={metrics.broken_wikilinks} orphan_notes={metrics.orphan_notes}")
    if report.broken_links:
        print("    broken_links(sample):")
        for item in report.broken_links[:10]:
            print(f"      - {item.source} -> [[{item.target}]]")
    if report.orphan_paths:
        print("    orphan_paths(sample):")
        for item in report.orphan_paths[:10]:
            print(f"      - {item}")
    return 0


def _vault(args) -> int:
    from pathlib import Path

    from hive_mind.maintenance.vault_frontmatter import repair_invalid_frontmatter
    from hive_mind.maintenance.vault_encoding import repair_legacy_encoding
    from hive_mind.maintenance.vault_project_id import repair_missing_project_id

    if args.vault_command == "repair-frontmatter":
        root = Path(args.vault_root) if args.vault_root else Path(os.environ.get("SINAPSE_HOME", Path.cwd())) / "cerebro"
        report = repair_invalid_frontmatter(vault_root=root, apply=args.apply)
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0
        mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
        print(f"hive-mind vault repair-frontmatter — {mode}\n")
        print(f"  vault_root={report.vault_root}")
        print(f"  scanned={report.scanned} candidates={report.candidates} repaired={report.repaired} "
              f"unchanged={report.unchanged} failed={report.failed}")
        for entry in report.entries[:20]:
            print(f"  - {entry.status}: {entry.path} ({entry.reason})")
        return 0

    if args.vault_command == "repair-project-id":
        root = Path(args.vault_root) if args.vault_root else Path(os.environ.get("SINAPSE_HOME", Path.cwd())) / "cerebro"
        report = repair_missing_project_id(vault_root=root, apply=args.apply)
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0
        mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
        print(f"hive-mind vault repair-project-id — {mode}\n")
        print(f"  vault_root={report.vault_root}")
        print(f"  scanned={report.scanned} candidates={report.candidates} repaired={report.repaired} "
              f"unchanged={report.unchanged} failed={report.failed}")
        for entry in report.entries[:20]:
            target = f" -> {entry.project_id}" if entry.project_id else ""
            print(f"  - {entry.status}: {entry.path}{target} ({entry.reason})")
        return 0

    if args.vault_command == "repair-encoding":
        root = Path(args.vault_root) if args.vault_root else Path(os.environ.get("SINAPSE_HOME", Path.cwd())) / "cerebro"
        report = repair_legacy_encoding(vault_root=root, apply=args.apply)
        if args.json:
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            return 0
        mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
        print(f"hive-mind vault repair-encoding — {mode}\n")
        print(f"  vault_root={report.vault_root}")
        print(f"  scanned={report.scanned} candidates={report.candidates} repaired={report.repaired} "
              f"unchanged={report.unchanged} failed={report.failed}")
        for entry in report.entries[:20]:
            print(f"  - {entry.status}: {entry.path} ({entry.reason})")
        return 0

    print("usage: hive-mind vault {repair-frontmatter|repair-project-id|repair-encoding}", file=sys.stderr)
    return 1


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
    if args.agents_command == "doctor":
        return _agents_doctor(args)
    if args.agents_command == "unregister":
        return _agents_unregister(args)

    print("usage: hive-mind agents {detect|list|register|doctor|unregister}",
          file=sys.stderr)
    return 1


def _agents_env():
    """(home, appdata) from the environment, resolved once."""
    from pathlib import Path

    home = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
    return home, Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))


def _agents_doctor(args) -> int:
    from hive_mind.agents.doctor import diagnose

    try:
        root = resolve_project_root(cli_root=args.project_root)
    except ProjectRootNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EX_CONFIG
    home, appdata = _agents_env()
    only = getattr(args, "only", None)
    report = diagnose([only] if only else None,
                      home=home, appdata=appdata, project_root=root)

    if args.json:
        print(json.dumps(
            [{"provider": d.provider, "detected": d.detected,
              "registered": d.fully_registered, "healthy": d.healthy,
              "instructions": d.instructions_installed,
              "configs": [c.__dict__ for c in d.configs]} for d in report],
            ensure_ascii=False, indent=2,
        ))
        return 0 if all(d.healthy for d in report) else 1

    print("hive-mind agents doctor — read-only\n")
    print(f"{'':4}{'PROVIDER':<12} {'DETECTED':<9} {'REGISTERED':<11} INSTRUCTIONS")
    unhealthy = 0
    for d in report:
        if not d.detected:
            continue
        mark = "OK  " if d.healthy else "WARN"
        unhealthy += 0 if d.healthy else 1
        inst = "yes" if d.instructions_installed else ("n/a" if not d.instruction_path else "no")
        print(f"{mark}{d.provider:<12} {'yes':<9} "
              f"{('yes' if d.fully_registered else 'no'):<11} {inst}")
    detected = [d for d in report if d.detected]
    print(f"\n{len(detected) - unhealthy} of {len(detected)} detected providers healthy")
    return 0 if unhealthy == 0 else 1


def _agents_unregister(args) -> int:
    from hive_mind.agents.detect import detect_providers
    from hive_mind.agents.doctor import unregister_providers

    try:
        root = resolve_project_root(cli_root=args.project_root)
    except ProjectRootNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EX_CONFIG
    home, appdata = _agents_env()
    targets = [args.only] if args.only else [r.id for r in detect_providers() if r.detected]
    if not targets:
        print("no providers detected", file=sys.stderr)
        return 1
    try:
        results = unregister_providers(
            targets, home=home, appdata=appdata, project_root=root,
            dry_run=not args.apply, remove_instruction_block=args.instructions,
        )
    except KeyError as exc:
        print(f"unknown provider: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2))
        return 0
    mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
    print(f"hive-mind agents unregister — {mode}\n")
    for r in results:
        state = "would remove" if not args.apply and r.changed else (
            "removed" if r.changed else "not present")
        print(f"  {'OK ' if r.changed else '== '}  {r.provider:<10} {r.path}  [{state}]")
    if not args.apply:
        print("\nRe-run with --apply to write these changes.")
    return 0


def _agents_register(args) -> int:
    """Register the MCP server with detected providers. Dry-run unless --apply."""
    import sys as _sys
    from pathlib import Path

    from hive_mind.agents import compat
    from hive_mind.agents.detect import detect_providers
    from hive_mind.agents.register import register_providers

    if args.list:
        print(" ".join(compat.LEGACY_AGENT_KEYS))
        return 0

    selected = compat.selected_provider(args)
    problem = compat.validate_provider(selected)
    if problem:
        print(problem, file=sys.stderr)
        return compat.EX_UNKNOWN_AGENT

    # `--check` is a diagnosis, and diagnosis has exactly one implementation.
    # Re-deriving it here would be the second registrar D009-R6 exists to avoid.
    if args.check:
        args.only = selected
        return _agents_doctor(args)

    try:
        root = resolve_project_root(cli_root=args.project_root)
    except ProjectRootNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EX_CONFIG

    if selected:
        targets = [selected]
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

    instructions = _install_instructions_for(
        targets, root, dry_run=not args.apply
    ) if compat.instructions_requested(args) else []

    if args.json:
        print(json.dumps(
            {"configs": [r.__dict__ for r in results],
             "instructions": [r.__dict__ for r in instructions]},
            ensure_ascii=False, indent=2,
        ))
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
    for r in instructions:
        state = "would write" if not args.apply and r.changed else (
            "written" if r.changed else "already current")
        print(f"  {'OK ' if r.changed else '== '}  {r.provider:<10} {r.path}  [{state}]")
    if not args.apply:
        print("\nRe-run with --apply to write these configs.")
    return 0


def _install_instructions_for(targets, root, *, dry_run: bool):
    """Install the managed instruction block for each provider that has one.

    The legacy registrars did this by default; `--instructions` was declared
    natively in D009-R5 but never wired, so the flag silently did nothing.
    """
    from hive_mind.agents.instructions import install_instructions
    from hive_mind.agents.registry import get_provider

    prompt_file = root / "config" / "sinapse-agent-prompt.md"
    if not prompt_file.is_file():
        print(f"instruction source not found: {prompt_file}", file=sys.stderr)
        return []
    prompt = prompt_file.read_text(encoding="utf-8-sig")

    results = []
    for provider_id in targets:
        spec = get_provider(provider_id)
        if not spec.prompt_target:
            continue
        results.append(install_instructions(
            provider_id, root / spec.prompt_target, prompt, dry_run=dry_run
        ))
    return results


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
    """Read-only view of the daemon state. Mutates nothing."""
    from pathlib import Path
    from hive_mind.daemon.control import ControlClient, ControlRequest
    from hive_mind.daemon.state import expected_state_paths, read_state, service_records

    def _legacy_supervisor_state(root: Path | None) -> dict | None:
        if root is None:
            return None
        state_path = root / "logs" / "supervisor" / "state.json"
        manifest_path = root / "logs" / "supervisor" / "manifest.json"
        if not state_path.exists():
            return None
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        manifest = {}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}

        services = {}
        required_map = {}
        for svc in manifest.get("services", []):
            if isinstance(svc, dict) and svc.get("name"):
                required_map[str(svc["name"])] = bool(svc.get("required"))

        for name, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            state = str(payload.get("state") or "").strip().lower()
            pid = payload.get("pid")
            running = state == "healthy"
            services[name] = {
                "state": "running" if running else state or "unknown",
                "pid": pid if isinstance(pid, int) else None,
                "returncode": None,
                "ownership": "legacy-supervisor",
                "required": required_map.get(name, False),
                "readiness": "ready" if running else state or "unknown",
                "updated_at": payload.get("updated_at"),
                "adopted": bool(payload.get("adopted", False)),
            }

        ready = all(
            svc.get("readiness") == "ready"
            for svc in services.values()
            if svc.get("required")
        )
        return {
            "mode": "legacy-supervisor",
            "profile": os.environ.get("HIVE_MIND_PROFILE", "local-min"),
            "ready": ready,
            "services": services,
        }

    if args.state_dir:
        state_dir = Path(args.state_dir)
        try:
            root = state_dir.parents[1]
        except IndexError:
            root = None
    else:
        try:
            root = resolve_project_root(cli_root=args.project_root)
        except ProjectRootNotFound as exc:
            print(str(exc), file=sys.stderr)
            return EX_CONFIG
        state_dir = root / ".hive-mind" / "state"

    managed_path, shadow_path = expected_state_paths(state_dir)
    state = None
    control_reachable = False
    if managed_path.exists():
        try:
            resp = ControlClient(state_dir=state_dir).request(
                ControlRequest(command="status"), timeout=3.0
            )
        except ConnectionError:
            resp = None
        if resp and resp.ok:
            control_reachable = True
            state = resp.data
    legacy_state = _legacy_supervisor_state(root)
    if state is None and control_reachable:
        state = read_state(state_dir)
    if state is None and legacy_state is not None:
        state = legacy_state
    if state is None:
        state = read_state(state_dir)
    if state is None:
        print(
            "no daemon state found; expected one of "
            f"{managed_path} or {shadow_path}",
            file=sys.stderr,
        )
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
    for svc in service_records(state):
        print(
            f"{svc.get('name', ''):<28} {svc.get('ownership', ''):<9} "
            f"{'yes' if svc.get('required') else 'no':<4} "
            f"{svc.get('readiness', ''):<10} {svc.get('startup_order', '')}"
        )
    return 0


def _service_windows_jobs(args) -> int:
    from hive_mind.maintenance.windows_jobs import register_windows_jobs

    try:
        root = resolve_project_root(cli_root=args.project_root)
    except ProjectRootNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EX_CONFIG

    report = register_windows_jobs(
        root=root,
        apply=args.apply,
        backup_dir=args.backup_dir,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0

    mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
    print(f"hive-mind service windows-jobs — {mode}\n")
    print(f"  project_root={report.project_root}")
    print(f"  backup_dir={report.backup_dir}")
    print(f"  scanned={report.scanned} registered={report.registered} skipped={report.skipped}")
    for entry in report.entries:
        print(f"  - {entry.status}: {entry.name}")
        print(f"    execute={entry.execute}")
        if entry.arguments:
            print(f"    arguments={entry.arguments}")
        if entry.source_script:
            print(f"    source_script={entry.source_script}")
        print(f"    reason={entry.reason}")
        if entry.backup_path:
            print(f"    backup={entry.backup_path}")
    return 0


def _service_windows_runtime(args) -> int:
    from hive_mind.maintenance.windows_runtime import register_windows_runtime

    try:
        root = resolve_project_root(cli_root=args.project_root)
    except ProjectRootNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EX_CONFIG

    report = register_windows_runtime(root=root, apply=args.apply)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0

    mode = "APPLIED" if args.apply else "DRY-RUN (nothing written)"
    print(f"hive-mind service windows-runtime — {mode}\n")
    print(f"  project_root={report.project_root}")
    print(f"  registered={report.registered} skipped={report.skipped}")
    for entry in report.entries:
        print(f"  - {entry.status}: {entry.name}")
        print(f"    execute={entry.execute}")
        if entry.arguments:
            print(f"    arguments={entry.arguments}")
        print(f"    reason={entry.reason}")
    return 0


def _service_manifest(args) -> int:
    from hive_mind.maintenance.runtime_services import manifest as runtime_manifest

    try:
        resolve_project_root(cli_root=args.project_root)
    except ProjectRootNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EX_CONFIG

    data = runtime_manifest()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print("hive-mind service manifest\n")
    print(f"  manifest_version={data['manifest_version']}")
    print(f"  root={data['root']}")
    print(f"  claude_mem_plugin_available={data['claude_mem_plugin_available']}")
    print(f"  services={len(data['services'])}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
