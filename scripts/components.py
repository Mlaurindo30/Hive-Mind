#!/usr/bin/env python3
"""Manage pinned embedded components without global package installs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "config" / "components.lock.json"
BACKUPS = ROOT / "config" / "component-lock-backups"


def run(*args: str, cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def succeeds(*args: str, cwd: Path | None = None) -> bool:
    return subprocess.run(
        args,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def load_lock(path: Path = LOCK) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or not data.get("components"):
        raise SystemExit(f"invalid component manifest: {path}")
    return data


def is_dirty(path: Path) -> bool:
    return bool(run("git", "status", "--porcelain", cwd=path, capture=True))


def head(path: Path) -> str:
    return run("git", "rev-parse", "HEAD", cwd=path, capture=True)


def component_patch(spec: dict) -> Path | None:
    value = spec.get("patch")
    return ROOT / value if value else None


def patch_is_applied(target: Path, patch: Path) -> bool:
    return succeeds(
        "git", "apply", "--unidiff-zero", "--reverse", "--check", str(patch),
        cwd=target,
    )


def apply_component_patch(name: str, spec: dict) -> None:
    patch = component_patch(spec)
    if patch is None:
        return
    if not patch.is_file():
        raise SystemExit(f"{name}: component patch missing: {patch}")
    target = ROOT / name
    if patch_is_applied(target, patch):
        return
    if not succeeds(
        "git", "apply", "--unidiff-zero", "--check", str(patch), cwd=target
    ):
        raise SystemExit(
            f"{name}: pinned patch does not apply to commit {head(target)}"
        )
    run("git", "apply", "--unidiff-zero", str(patch), cwd=target)
    print(f"[components] applied {patch.relative_to(ROOT)} to {name}")


def remove_component_patch(name: str, spec: dict) -> None:
    patch = component_patch(spec)
    if patch is None:
        return
    target = ROOT / name
    if not patch_is_applied(target, patch):
        raise SystemExit(f"{name}: expected pinned patch is not applied")
    run("git", "apply", "--unidiff-zero", "--reverse", str(patch), cwd=target)


def clone_pinned(name: str, spec: dict) -> None:
    target = ROOT / name
    if target.exists():
        if not (target / ".git").exists():
            raise SystemExit(f"{target} exists but is not a Git checkout")
        return

    print(f"[components] cloning {name} at {spec['commit']}")
    run("git", "clone", "--filter=blob:none", "--no-checkout", spec["repository"], str(target))
    try:
        run("git", "fetch", "--depth", "1", "origin", spec["commit"], cwd=target)
        run("git", "checkout", "--detach", spec["commit"], cwd=target)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def bootstrap(args: argparse.Namespace) -> int:
    data = load_lock()
    for name, spec in data["components"].items():
        clone_pinned(name, spec)
        actual = head(ROOT / name)
        if actual != spec["commit"]:
            message = f"{name}: expected {spec['commit']}, found {actual}"
            if args.strict:
                raise SystemExit(message)
            print(f"[components] WARNING {message}; preserving existing checkout", file=sys.stderr)
        else:
            apply_component_patch(name, spec)
    return 0


def verify(_: argparse.Namespace) -> int:
    data = load_lock()
    failed = False
    for name, spec in data["components"].items():
        target = ROOT / name
        if not (target / ".git").exists():
            print(f"FAIL {name}: checkout missing")
            failed = True
            continue
        actual = head(target)
        dirty = is_dirty(target)
        patch = component_patch(spec)
        patch_ok = patch is None or (patch.is_file() and patch_is_applied(target, patch))
        status = "OK" if actual == spec["commit"] else "DRIFT"
        print(
            f"{status} {name}: version={spec['version']} "
            f"expected={spec['commit']} actual={actual} dirty={str(dirty).lower()} "
            f"patch={'ok' if patch_ok else 'missing'}"
        )
        failed |= actual != spec["commit"] or not patch_ok
    return 1 if failed else 0


def snapshot_lock() -> Path:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = BACKUPS / f"components.lock.{stamp}.json"
    shutil.copy2(LOCK, destination)
    return destination


def update(args: argparse.Namespace) -> int:
    data = load_lock()
    names = list(data["components"]) if args.component == "all" else [args.component]
    unknown = [name for name in names if name not in data["components"]]
    if unknown:
        raise SystemExit(f"unknown component: {', '.join(unknown)}")

    for name in names:
        target = ROOT / name
        if not (target / ".git").exists():
            raise SystemExit(f"{name}: checkout missing; run bootstrap first")
        patch = component_patch(data["components"][name])
        if patch is not None:
            remove_component_patch(name, data["components"][name])
        unexpected_dirty = is_dirty(target)
        if patch is not None:
            apply_component_patch(name, data["components"][name])
        if unexpected_dirty:
            raise SystemExit(f"{name}: dirty checkout beyond the pinned patch")

    backup = snapshot_lock()
    print(f"[components] manifest backup: {backup}")
    for name in names:
        target = ROOT / name
        spec = data["components"][name]
        old_commit = spec["commit"]
        if component_patch(spec) is not None:
            remove_component_patch(name, spec)
        run("git", "fetch", "--prune", "origin", cwd=target)
        remote_head = run("git", "rev-parse", "origin/HEAD", cwd=target, capture=True)
        try:
            run("git", "checkout", "--detach", remote_head, cwd=target)
            apply_component_patch(name, spec)
        except BaseException:
            run("git", "checkout", "--detach", old_commit, cwd=target)
            apply_component_patch(name, spec)
            raise
        spec["commit"] = remote_head
        spec["version"] = f"commit:{remote_head[:12]}"
        print(f"[components] {name} -> {remote_head}")

    LOCK.write_text(json.dumps(data, indent=2) + "\n")
    print("[components] run uv lock && tests/run_all.sh before accepting the update")
    return 0


def rollback(args: argparse.Namespace) -> int:
    source = Path(args.manifest).resolve()
    if not source.is_file():
        raise SystemExit(f"rollback manifest not found: {source}")
    current = load_lock()
    data = load_lock(source)
    for name, spec in data["components"].items():
        target = ROOT / name
        if name in current["components"] and component_patch(current["components"][name]):
            remove_component_patch(name, current["components"][name])
        if is_dirty(target):
            raise SystemExit(f"{name}: dirty checkout; refusing rollback")
        run("git", "fetch", "origin", spec["commit"], cwd=target)
        run("git", "checkout", "--detach", spec["commit"], cwd=target)
        apply_component_patch(name, spec)
    shutil.copy2(source, LOCK)
    print(f"[components] rolled back using {source}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = sub.add_parser("bootstrap")
    bootstrap_parser.add_argument("--strict", action="store_true")
    bootstrap_parser.set_defaults(func=bootstrap)

    verify_parser = sub.add_parser("verify")
    verify_parser.set_defaults(func=verify)

    update_parser = sub.add_parser("update")
    update_parser.add_argument("--component", default="all")
    update_parser.set_defaults(func=update)

    rollback_parser = sub.add_parser("rollback")
    rollback_parser.add_argument("manifest")
    rollback_parser.set_defaults(func=rollback)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
