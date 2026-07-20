"""Hive-Mind daemon entry point (F1 stub).

The F1 scope only registers ``hive-mindd --version``,
``hive-mindd --help``, and ``hive-mindd run`` (which **fails** with
``EX_UNAVAILABLE=69`` because the daemon is not implemented in F1).
**No** processes are spawned; **no** services are started; **no**
manifest is parsed.

Real implementation lands in F3 (daemon) onwards.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

EX_UNAVAILABLE = 69  # sysexits.h


def _get_version() -> str:
    """Return the installed package version.

    The single source of truth is ``pyproject.toml::project.version``,
    read at runtime via importlib.metadata.
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
        prog="hive-mindd",
        description="Hive-Mind control plane daemon.",
    )
    p.add_argument("--version", action="store_true", help="print the daemon version and exit")
    sub = p.add_subparsers(dest="command")
    run = sub.add_parser("run", help="run the daemon")
    run.add_argument(
        "--shadow",
        action="store_true",
        help="passive shadow pass: observe the manifest, write shadow state, "
        "start nothing (spec F3 / Anexo D.4)",
    )
    run.add_argument("--manifest", default=None, help="path to config/runtime.yaml")
    run.add_argument("--state-dir", default=None, help="daemon state directory")
    run.add_argument("--project-root", default=None, help="project root override")
    return p


def _resolve_paths(args) -> "tuple[Path, Path]":
    """Return (manifest_path, state_dir), honouring overrides then the root."""
    from hive_mind.project import resolve_project_root

    root = resolve_project_root(cli_root=args.project_root)
    manifest_path = (
        Path(args.manifest) if args.manifest else root / "config" / "runtime.yaml"
    )
    state_dir = Path(args.state_dir) if args.state_dir else root / ".hive-mind" / "state"
    return manifest_path, state_dir


def _run_shadow(args) -> int:
    """One passive shadow pass. Acquires the single-instance lock, observes,
    writes shadow state, releases. Starts nothing."""
    from hive_mind.daemon.lock import SingleInstanceLock, SingleInstanceLockError
    from hive_mind.daemon.manifest import load_manifest
    from hive_mind.daemon.supervisor import ShadowSupervisor

    manifest_path, state_dir = _resolve_paths(args)
    try:
        manifest = load_manifest(manifest_path)
    except FileNotFoundError as exc:
        print(f"hive-mindd: {exc}", file=sys.stderr)
        return EX_UNAVAILABLE

    try:
        with SingleInstanceLock(state_dir):
            summary = ShadowSupervisor(manifest, state_dir=state_dir).observe()
    except SingleInstanceLockError as exc:
        print(f"hive-mindd: {exc}", file=sys.stderr)
        return EX_UNAVAILABLE

    ready = "ready" if summary["ready"] else "not-ready"
    print(
        f"hive-mindd shadow: profile={summary['profile']} "
        f"services={summary['service_count']} required={ready} "
        f"-> {state_dir / 'services.shadow.json'}"
    )
    return 0


def main(argv: "list[str] | None" = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"hive-mindd {_get_version()}")
        return 0
    if args.command == "run":
        if getattr(args, "shadow", False):
            return _run_shadow(args)
        print(
            "hive-mindd run (managed) is not implemented yet; "
            "use --shadow for the passive pass",
            file=sys.stderr,
        )
        return EX_UNAVAILABLE
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
