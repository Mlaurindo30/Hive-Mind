from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def _is_within(path: Path, directory: Path) -> bool:
    try:
        return path.resolve().is_relative_to(directory.resolve())
    except ValueError:
        return False


def project_python_home(root: str | Path) -> Path | None:
    root = Path(root).resolve()
    config = root / ".venv" / "pyvenv.cfg"
    try:
        for raw in config.read_text(encoding="utf-8", errors="replace").splitlines():
            key, separator, value = raw.partition("=")
            if separator and key.strip().lower() == "home":
                return Path(value.strip()).resolve()
    except OSError:
        return None
    return None


def project_python_home_is_local(root: str | Path) -> bool:
    root = Path(root).resolve()
    home = project_python_home(root)
    return home is not None and _is_within(home, root / ".uv" / "python")


def test_python_version(version: str) -> bool:
    parts = version.strip().split()
    if len(parts) < 2 or parts[0] != "Python":
        return False
    try:
        major, minor, *_rest = parts[1].split(".")
    except ValueError:
        return False
    return int(major) == 3 and int(minor) == 12


def test_python_runtime(root: str | Path) -> bool:
    root = Path(root).resolve()
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        return False
    result = subprocess.run(
        [str(python), "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return (
        test_python_version((result.stdout or result.stderr).strip())
        and project_python_home_is_local(root)
    )


def project_uv_environment(root: str | Path) -> dict[str, str]:
    root = Path(root).resolve()
    environment = os.environ.copy()
    environment["UV_CACHE_DIR"] = str(root / ".uv" / "cache")
    environment["UV_PYTHON_INSTALL_DIR"] = str(root / ".uv" / "python")
    return environment


def repair_python_runtime(root: str | Path) -> None:
    root = Path(root).resolve()
    environment = project_uv_environment(root)
    first = subprocess.run(
        ["uv", "python", "install", "3.12"],
        text=True,
        check=False,
        env=environment,
    )
    if first.returncode != 0:
        raise RuntimeError("uv could not provision Python 3.12")
    second = subprocess.run(
        ["uv", "venv", "--python", "3.12", "--clear", str(root / ".venv")],
        text=True,
        check=False,
        env=environment,
    )
    if second.returncode != 0:
        raise RuntimeError("uv could not create the project virtual environment")


def ensure_python_runtime(root: str | Path) -> None:
    if not test_python_runtime(root):
        repair_python_runtime(root)


def read_dotenv(root: str | Path) -> dict[str, str]:
    root = Path(root).resolve()
    env_path = root / ".env"
    values: dict[str, str] = {}
    if not env_path.is_file():
        return values
    for raw in env_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def set_dotenv_value(root: str | Path, name: str, value: str) -> None:
    root = Path(root).resolve()
    env_path = root / ".env"
    lines = env_path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if env_path.is_file() else []
    pattern = f"{name}="
    updated = False
    next_lines: list[str] = []
    for line in lines:
        if line.lstrip().startswith(pattern):
            next_lines.append(f"{name}={value}")
            updated = True
        else:
            next_lines.append(line)
    if not updated:
        next_lines.append(f"{name}={value}")
    env_path.write_text("\n".join(next_lines) + ("\n" if next_lines else ""), encoding="utf-8")


def apply_profile_contract(root: str | Path, profile_contract: str | Path, *, dry_run: bool = False) -> list[str]:
    root = Path(root).resolve()
    profile_contract = Path(profile_contract).resolve()
    if not profile_contract.is_file():
        raise FileNotFoundError(f"Profile contract was not found: {profile_contract}")
    applied: list[str] = []
    for raw in profile_contract.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        if any(token in name.lower() for token in ("api_key", "token", "secret", "password", "credential")):
            continue
        applied.append(name)
        if not dry_run:
            set_dotenv_value(root, name, value)
    return applied


def sync_vault_templates(root: str | Path) -> None:
    root = Path(root).resolve()
    template_vault = root / "templates" / "vault"
    if not template_vault.is_dir():
        raise FileNotFoundError(f"Shipped vault template directory was not found: {template_vault}")
    vault = root / "cerebro"
    vault.mkdir(parents=True, exist_ok=True)
    for source in template_vault.rglob("*"):
        relative = source.relative_to(template_vault)
        destination = vault / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hive-Mind native Windows support owner")
    sub = parser.add_subparsers(dest="command", required=True)

    ensure = sub.add_parser("ensure-python-runtime")
    ensure.add_argument("--root", required=True)

    test_cmd = sub.add_parser("test-python-runtime")
    test_cmd.add_argument("--root", required=True)

    repair_cmd = sub.add_parser("repair-python-runtime")
    repair_cmd.add_argument("--root", required=True)

    apply_cmd = sub.add_parser("apply-profile-contract")
    apply_cmd.add_argument("--root", required=True)
    apply_cmd.add_argument("--profile-contract", required=True)
    apply_cmd.add_argument("--dry-run", action="store_true")

    set_cmd = sub.add_parser("set-dotenv-value")
    set_cmd.add_argument("--root", required=True)
    set_cmd.add_argument("--name", required=True)
    set_cmd.add_argument("--value", required=True)

    read_cmd = sub.add_parser("read-dotenv")
    read_cmd.add_argument("--root", required=True)

    sync_cmd = sub.add_parser("sync-vault-templates")
    sync_cmd.add_argument("--root", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "ensure-python-runtime":
        ensure_python_runtime(args.root)
        return 0
    if args.command == "test-python-runtime":
        print(json.dumps({"Ready": test_python_runtime(args.root)}))
        return 0
    if args.command == "repair-python-runtime":
        repair_python_runtime(args.root)
        return 0
    if args.command == "apply-profile-contract":
        print(json.dumps(apply_profile_contract(args.root, args.profile_contract, dry_run=args.dry_run), ensure_ascii=False))
        return 0
    if args.command == "set-dotenv-value":
        set_dotenv_value(args.root, args.name, args.value)
        return 0
    if args.command == "read-dotenv":
        print(json.dumps(read_dotenv(args.root), ensure_ascii=False))
        return 0
    sync_vault_templates(args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
