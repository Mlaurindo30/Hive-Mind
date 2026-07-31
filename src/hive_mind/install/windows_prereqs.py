from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Prerequisite:
    name: str
    winget_id: str | None
    command: str
    required: bool
    installed: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PrerequisiteBootstrapResult:
    ready: bool
    restart_required: bool
    missing: tuple[Prerequisite, ...]
    installed: tuple[Prerequisite, ...]

    def to_legacy_dict(self) -> dict[str, object]:
        return {
            "Ready": self.ready,
            "RestartRequired": self.restart_required,
            "Missing": [entry.to_dict() for entry in self.missing],
            "Installed": [entry.to_dict() for entry in self.installed],
        }


def _run_command(file: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [file, *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def _find_command(name: str) -> str | None:
    return shutil.which(name)


def _vswhere() -> Path | None:
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", ""))
    candidate = program_files_x86 / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    return candidate if candidate.is_file() else None


def test_visual_studio_build_tools() -> bool:
    vswhere = _vswhere()
    if vswhere is None:
        return False
    result = _run_command(
        str(vswhere),
        ["-products", "*", "-requires", "Microsoft.Component.MSBuild", "-property", "installationPath"],
    )
    return bool(result.returncode == 0 and result.stdout.strip())


def get_visual_studio_msbuild_directory() -> str | None:
    vswhere = _vswhere()
    if vswhere is None:
        return None
    result = _run_command(
        str(vswhere),
        ["-products", "*", "-requires", "Microsoft.Component.MSBuild", "-property", "installationPath"],
    )
    installation_path = result.stdout.strip()
    if not installation_path:
        return None
    directory = Path(installation_path) / "MSBuild" / "Current" / "Bin"
    return str(directory) if directory.is_dir() else None


def update_prerequisite_path() -> None:
    locations: list[str] = []
    local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
    userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", ""))
    for candidate in (
        local_appdata / "Microsoft" / "WinGet" / "Links",
        userprofile / ".local" / "bin",
        userprofile / ".bun" / "bin",
        userprofile / ".cargo" / "bin",
        program_files_x86 / "Microsoft Visual Studio" / "2022" / "BuildTools" / "MSBuild" / "Current" / "Bin",
    ):
        if candidate.is_dir():
            locations.append(str(candidate))
    visual_studio_msbuild = get_visual_studio_msbuild_directory()
    if visual_studio_msbuild:
        locations.append(visual_studio_msbuild)
    winget_packages = local_appdata / "Microsoft" / "WinGet" / "Packages"
    if winget_packages.is_dir():
        for exe_name in ("uv.exe", "bun.exe", "syncthing.exe"):
            for found in winget_packages.rglob(exe_name):
                locations.append(str(found.parent))
    unique_locations = []
    seen = set()
    for location in locations:
        if location not in seen:
            seen.add(location)
            unique_locations.append(location)
    current = os.environ.get("PATH", "").split(";")
    for location in reversed(unique_locations):
        if location and location not in current:
            current.insert(0, location)
    os.environ["PATH"] = ";".join(part for part in current if part)


def get_prerequisites(profile: str) -> list[Prerequisite]:
    full_profile = profile == "local-full"
    items = [
        ("Git", "Git.Git", "git", True),
        ("uv", "astral-sh.uv", "uv", True),
        ("Bun", "Oven-sh.Bun", "bun", True),
        ("Node LTS", "OpenJS.NodeJS.LTS", "node", True),
        ("Rustup", "Rustlang.Rustup", "cargo", True),
        ("Ollama", "Ollama.Ollama", "ollama", True),
        ("Docker Desktop", "Docker.DockerDesktop", "docker", full_profile),
        ("Syncthing", "Syncthing.Syncthing", "syncthing", full_profile),
        ("WSL 2", None, "wsl", full_profile),
        ("Visual Studio Build Tools", "Microsoft.VisualStudio.2022.BuildTools", "msbuild", full_profile),
    ]
    prerequisites: list[Prerequisite] = []
    for name, winget_id, command, required in items:
        installed = test_visual_studio_build_tools() if name == "Visual Studio Build Tools" else _find_command(command) is not None
        prerequisites.append(
            Prerequisite(
                name=name,
                winget_id=winget_id,
                command=command,
                required=required,
                installed=installed,
                reason=f"command {command} is on PATH" if installed else f"command {command} not on PATH",
            )
        )
    return prerequisites


def _persist_restart_state(root: Path, profile: str) -> None:
    state_directory = root / "backups" / "install-state"
    state_directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "Profile": profile,
        "RestartRequired": True,
        "UpdatedAt": datetime.now(timezone.utc).isoformat(),
    }
    (state_directory / "prerequisites.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def invoke_prerequisite_bootstrap(
    *,
    root: str | Path,
    profile: str,
    dry_run: bool = False,
    skip_wsl: bool = False,
) -> PrerequisiteBootstrapResult:
    root = Path(root).resolve()
    update_prerequisite_path()
    prerequisites = get_prerequisites(profile)
    required = [item for item in prerequisites if item.required and not (skip_wsl and item.name == "WSL 2")]
    missing = [item for item in required if not item.installed]
    installed = [item for item in required if item.installed]
    if dry_run:
        return PrerequisiteBootstrapResult(not missing, False, tuple(missing), tuple(installed))

    if missing and _find_command("winget") is None:
        raise RuntimeError("winget is required to install Hive-Mind prerequisites. Install App Installer and run this command again.")

    restart_required = False
    for item in missing:
        if item.name == "WSL 2":
            result = _run_command("wsl", ["--install"])
        else:
            result = _run_command(
                "winget",
                ["install", "--id", str(item.winget_id), "--exact", "--silent", "--accept-source-agreements", "--accept-package-agreements"],
            )
        if result.returncode in (3010, 1641):
            restart_required = True
            _persist_restart_state(root, profile)
            return PrerequisiteBootstrapResult(False, True, tuple(missing), tuple(installed))
        if result.returncode != 0:
            output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            raise RuntimeError(f"Failed to install {item.name}: {output.strip()}")

    if not skip_wsl and profile == "local-full":
        status = _run_command("wsl", ["--status"])
        if status.returncode != 0:
            output = (status.stdout or "") + ("\n" + status.stderr if status.stderr else "")
            raise RuntimeError(f"WSL 2 validation failed: {output.strip()}")

    validations = [
        ("Docker Desktop", "docker", ["version"], profile == "local-full"),
        ("Ollama", "ollama", ["list"], True),
    ]
    for name, command, arguments, enabled in validations:
        if not enabled:
            continue
        result = _run_command(command, arguments)
        if result.returncode != 0:
            output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            raise RuntimeError(f"{name} validation failed: {output.strip()}")

    final = get_prerequisites(profile)
    final_required = [item for item in final if item.required and not (skip_wsl and item.name == "WSL 2")]
    final_missing = [item for item in final_required if not item.installed]
    final_installed = [item for item in final_required if item.installed]
    return PrerequisiteBootstrapResult(not final_missing and not restart_required, restart_required, tuple(final_missing), tuple(final_installed))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hive-Mind native Windows prerequisite management")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--profile", choices=("local-min", "local-full"), required=True)

    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--root", required=True)
    bootstrap.add_argument("--profile", choices=("local-min", "local-full"), required=True)
    bootstrap.add_argument("--dry-run", action="store_true")
    bootstrap.add_argument("--skip-wsl", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "list":
        print(json.dumps([item.to_dict() for item in get_prerequisites(args.profile)], ensure_ascii=False))
        return 0
    result = invoke_prerequisite_bootstrap(
        root=args.root,
        profile=args.profile,
        dry_run=args.dry_run,
        skip_wsl=args.skip_wsl,
    )
    print(json.dumps(result.to_legacy_dict(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
