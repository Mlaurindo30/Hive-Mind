"""Hive-Mind daemon entry point."""
from __future__ import annotations

import argparse
import time
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
    run.add_argument(
        "--serve",
        action="store_true",
        help="after the shadow pass, serve the read-only HTTP loopback "
        "(/health /ready /metrics) until interrupted",
    )
    run.add_argument("--host", default=None, help="HTTP bind host (default 127.0.0.1)")
    run.add_argument("--port", type=int, default=None, help="HTTP bind port (default 37780)")
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

    # The single-instance lock is held for the whole run: the shadow pass and,
    # when --serve is set, the serving loop too. A second daemon must fail while
    # the first is alive, not only during the brief observation.
    try:
        with SingleInstanceLock(state_dir):
            summary = ShadowSupervisor(manifest, state_dir=state_dir).observe()
            ready = "ready" if summary["ready"] else "not-ready"
            print(
                f"hive-mindd shadow: profile={summary['profile']} "
                f"services={summary['service_count']} required={ready} "
                f"-> {state_dir / 'services.shadow.json'}"
            )
            if getattr(args, "serve", False):
                return _serve(args, state_dir)
    except SingleInstanceLockError as exc:
        print(f"hive-mindd: {exc}", file=sys.stderr)
        return EX_UNAVAILABLE
    return 0


def _run_managed(args) -> int:
    """Managed runtime: own the service lifecycle via ManagedSupervisor."""
    from hive_mind.daemon.lock import SingleInstanceLock, SingleInstanceLockError
    from hive_mind.daemon.managed import ManagedSupervisor
    from hive_mind.daemon.manifest import load_manifest

    manifest_path, state_dir = _resolve_paths(args)
    try:
        manifest = load_manifest(manifest_path)
    except FileNotFoundError as exc:
        print(f"hive-mindd: {exc}", file=sys.stderr)
        return EX_UNAVAILABLE

    try:
        with SingleInstanceLock(state_dir):
            supervisor = ManagedSupervisor(manifest, state_dir=state_dir)
            supervisor.start_all()
            supervisor.start_monitor()
            status = supervisor.status()
            print(
                f"hive-mindd managed: profile={status['profile']} "
                f"services={len(status['services'])} "
                f"-> {state_dir / 'services.managed.json'}"
            )
            try:
                if getattr(args, "serve", False):
                    return _serve(
                        args,
                        state_dir,
                        mode="managed",
                        supervisor=supervisor,
                    )
                while True:
                    time.sleep(3600)
            finally:
                supervisor.stop_monitor()
                supervisor.stop_all()
    except SingleInstanceLockError as exc:
        print(f"hive-mindd: {exc}", file=sys.stderr)
        return EX_UNAVAILABLE


def _serve(args, state_dir: Path, *, mode: str, supervisor=None) -> int:
    """Serve the read-only HTTP loopback and the control socket until interrupted."""
    import threading

    import uvicorn

    from hive_mind.daemon.control import ControlServer
    from hive_mind.daemon.control_dispatch import (
        ManagedControlDispatcher,
        ShadowControlDispatcher,
    )
    from hive_mind.daemon.http_api import (
        DEFAULT_HTTP_HOST,
        DEFAULT_HTTP_PORT,
        create_app,
    )

    if mode == "managed":
        dispatcher = ManagedControlDispatcher(supervisor=supervisor, state_dir=state_dir)
    else:
        dispatcher = ShadowControlDispatcher(state_dir=state_dir)
    control = ControlServer(
        state_dir=state_dir, dispatch=dispatcher
    )
    control.start()
    control_thread = threading.Thread(target=control.serve_forever, daemon=True)
    control_thread.start()
    if mode == "managed":
        print("hive-mindd control socket ready (managed)")
    else:
        print("hive-mindd control socket ready (shadow: mutations refused)")

    host = args.host or DEFAULT_HTTP_HOST
    port = args.port or DEFAULT_HTTP_PORT
    app = create_app(state_dir=state_dir)
    print(f"hive-mindd http (read-only): http://{host}:{port}/health")
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        control.shutdown()
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
        if getattr(args, "serve", False):
            return _run_managed(args)
        print(
            "hive-mindd run (managed) is not implemented yet; "
            "use --serve for the managed daemon or --shadow for the passive pass",
            file=sys.stderr,
        )
        return EX_UNAVAILABLE
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
