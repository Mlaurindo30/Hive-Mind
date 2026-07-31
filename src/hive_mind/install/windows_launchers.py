"""Validation contract for installed Hive-Mind Windows GUI launchers."""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


IMAGE_SUBSYSTEM_WINDOWS_GUI = 2
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_PROBE_ARGUMENT = "--hive-mind-launcher-probe"


@dataclass(frozen=True)
class LauncherEvidence:
    name: str
    path: Path
    subsystem: int
    prefix: Path
    package_origin: Path
    sys_executable: Path


def read_pe_subsystem(path: str | Path) -> int:
    executable = Path(path)
    try:
        image = executable.read_bytes()
    except OSError as exc:
        raise ValueError(f"PE file could not be read: {executable}") from exc
    if len(image) < 64 or image[:2] != b"MZ":
        raise ValueError(f"not a valid PE image: {executable}")

    pe_offset = struct.unpack_from("<I", image, 0x3C)[0]
    file_header_offset = pe_offset + 4
    optional_header_offset = file_header_offset + 20
    if (
        pe_offset < 64
        or optional_header_offset + 2 > len(image)
        or image[pe_offset:file_header_offset] != b"PE\0\0"
    ):
        raise ValueError(f"truncated or invalid PE header: {executable}")

    try:
        optional_size = struct.unpack_from("<H", image, file_header_offset + 16)[0]
    except struct.error as exc:
        raise ValueError(f"truncated PE file header: {executable}") from exc
    subsystem_offset = optional_header_offset + 68
    if (
        optional_size < 70
        or optional_header_offset + optional_size > len(image)
        or subsystem_offset + 2 > len(image)
    ):
        raise ValueError(f"truncated PE optional header: {executable}")
    try:
        magic = struct.unpack_from("<H", image, optional_header_offset)[0]
    except struct.error as exc:
        raise ValueError(f"truncated PE optional header: {executable}") from exc
    if magic not in (0x10B, 0x20B):
        raise ValueError(f"unsupported PE optional header: {executable}")
    return struct.unpack_from("<H", image, subsystem_offset)[0]


def ensure_gui_pythonw(
    root: str | Path, *, base_prefix: str | Path | None = None
) -> Path:
    selected_root = Path(root).resolve()
    destination = selected_root / ".venv" / "Scripts" / "pythonw.exe"
    if base_prefix is None:
        from hive_mind.install.windows_support import project_python_home

        configured_home = project_python_home(selected_root)
        if configured_home is None:
            raise RuntimeError(
                f"project virtual environment has no configured Python home: "
                f"{selected_root / '.venv' / 'pyvenv.cfg'}"
            )
        source_root = configured_home
    else:
        source_root = Path(base_prefix).resolve()
    if not _is_within(source_root, selected_root / ".uv" / "python"):
        raise RuntimeError(
            f"base Python runtime is outside the selected project root: {source_root}"
        )
    source = source_root / "pythonw.exe"
    if not source.is_file():
        raise RuntimeError(f"base Python GUI interpreter is missing: {source}")
    try:
        source_subsystem = read_pe_subsystem(source)
    except ValueError as exc:
        raise RuntimeError(f"base Python GUI interpreter is invalid: {source}") from exc
    if source_subsystem != IMAGE_SUBSYSTEM_WINDOWS_GUI:
        raise RuntimeError(
            f"base Python GUI interpreter must use PE Subsystem 2, got "
            f"{source_subsystem}: {source}"
        )
    try:
        destination_subsystem = read_pe_subsystem(destination)
    except ValueError:
        destination_subsystem = None
    if destination_subsystem != IMAGE_SUBSYSTEM_WINDOWS_GUI:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    if read_pe_subsystem(destination) != IMAGE_SUBSYSTEM_WINDOWS_GUI:
        raise RuntimeError(f"project GUI interpreter is invalid: {destination}")
    return destination.resolve()


def expected_gui_launchers(root: str | Path) -> dict[str, Path]:
    scripts = Path(root).resolve() / ".venv" / "Scripts"
    return {
        "hive-mind-supervisorw": (scripts / "hive-mind-supervisorw.exe").resolve(),
        "hive-mind-post-rebootw": (
            scripts / "hive-mind-post-rebootw.exe"
        ).resolve(),
        "hive-mind-capture-hookw": (
            scripts / "hive-mind-capture-hookw.exe"
        ).resolve(),
    }


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _is_within(path: Path, directory: Path) -> bool:
    normalized_path = os.path.normcase(str(path.resolve()))
    normalized_directory = os.path.normcase(str(directory.resolve()))
    try:
        return os.path.commonpath([normalized_path, normalized_directory]) == normalized_directory
    except ValueError:
        return False


def _run_probe(executable: Path) -> dict[str, str]:
    probe_file = tempfile.NamedTemporaryFile(
        prefix="hive-mind-gui-probe-",
        suffix=".json",
        delete=False,
    )
    probe_path = Path(probe_file.name)
    probe_file.close()
    probe_path.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            [str(executable), _PROBE_ARGUMENT, str(probe_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                f"GUI launcher probe failed for {executable} "
                f"(exit {result.returncode}): {detail}"
            )
        try:
            payload = json.loads(probe_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"GUI launcher probe produced no valid evidence for {executable}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"GUI launcher probe produced invalid evidence for {executable}"
            )
        return payload
    finally:
        probe_path.unlink(missing_ok=True)


def validate_gui_launchers(
    root: str | Path,
) -> tuple[LauncherEvidence, ...]:
    selected_root = Path(root).resolve()
    expected_prefix = (selected_root / ".venv").resolve()
    expected_package_root = (selected_root / "src" / "hive_mind").resolve()
    evidence: list[LauncherEvidence] = []
    for name, executable in expected_gui_launchers(selected_root).items():
        if not executable.is_file():
            raise RuntimeError(f"required GUI launcher is missing: {executable}")
        try:
            subsystem = read_pe_subsystem(executable)
        except ValueError as exc:
            raise RuntimeError(f"GUI launcher is not a valid PE image: {executable}") from exc
        if subsystem != IMAGE_SUBSYSTEM_WINDOWS_GUI:
            raise RuntimeError(
                f"GUI launcher must use PE Subsystem 2, got {subsystem}: {executable}"
            )

        payload = _run_probe(executable)
        try:
            prefix = Path(payload["sys_prefix"]).resolve()
            package_origin = Path(payload["package_origin"]).resolve()
            sys_executable = Path(payload["sys_executable"]).resolve()
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"GUI launcher probe evidence is incomplete: {executable}"
            ) from exc
        if not _same_path(prefix, expected_prefix):
            raise RuntimeError(
                f"GUI launcher sys.prefix is outside the selected .venv: "
                f"{prefix} != {expected_prefix}"
            )
        if not _is_within(sys_executable, expected_prefix):
            raise RuntimeError(
                f"GUI launcher sys.executable is outside the selected .venv: "
                f"{sys_executable}"
            )
        try:
            interpreter_subsystem = read_pe_subsystem(sys_executable)
        except ValueError as exc:
            raise RuntimeError(
                f"GUI launcher interpreter is not a valid PE image: "
                f"{sys_executable}"
            ) from exc
        if interpreter_subsystem != IMAGE_SUBSYSTEM_WINDOWS_GUI:
            raise RuntimeError(
                f"GUI launcher interpreter must use PE Subsystem 2, got "
                f"{interpreter_subsystem}: {sys_executable}"
            )
        if not _is_within(package_origin, expected_package_root):
            raise RuntimeError(
                f"GUI launcher package origin is outside the selected source package: "
                f"{package_origin}"
            )
        evidence.append(
            LauncherEvidence(
                name=name,
                path=executable,
                subsystem=subsystem,
                prefix=prefix,
                package_origin=package_origin,
                sys_executable=sys_executable,
            )
        )
    return tuple(evidence)
