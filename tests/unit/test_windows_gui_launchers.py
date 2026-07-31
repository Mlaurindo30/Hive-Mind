from __future__ import annotations

import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from hive_mind.install.windows_launchers import (
    ensure_gui_pythonw,
    expected_gui_launchers,
    read_pe_subsystem,
    validate_gui_launchers,
)


def _write_pe(path: Path, subsystem: int) -> None:
    optional_header = bytearray(70)
    struct.pack_into("<H", optional_header, 0, 0x20B)
    struct.pack_into("<H", optional_header, 68, subsystem)
    image = bytearray(0x80)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    image.extend(b"PE\0\0")
    image.extend(struct.pack("<HHIIIHH", 0x8664, 0, 0, 0, 0, len(optional_header), 0))
    image.extend(optional_header)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image)


@pytest.mark.parametrize("subsystem", [2, 3])
def test_read_pe_subsystem_returns_declared_value(tmp_path: Path, subsystem: int):
    executable = tmp_path / "launcher.exe"
    _write_pe(executable, subsystem)

    assert read_pe_subsystem(executable) == subsystem


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"not-a-pe",
        b"MZ" + bytes(60),
        b"MZ" + bytes(58) + struct.pack("<I", 0x1000),
        b"MZ" + bytes(58) + struct.pack("<I", 0x40) + b"NOPE",
    ],
)
def test_read_pe_subsystem_rejects_malformed_or_truncated_files(
    tmp_path: Path, payload: bytes
):
    executable = tmp_path / "broken.exe"
    executable.write_bytes(payload)

    with pytest.raises(ValueError):
        read_pe_subsystem(executable)


def test_read_pe_subsystem_normalizes_partial_coff_header_to_value_error(
    tmp_path: Path,
):
    executable = tmp_path / "partial-header.exe"
    image = bytearray(0x84)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    executable.write_bytes(image)

    with pytest.raises(ValueError):
        read_pe_subsystem(executable)


def test_expected_gui_launchers_are_rooted_in_selected_project_venv(tmp_path: Path):
    expected = expected_gui_launchers(tmp_path)

    assert expected == {
        "hive-mind-capture-hookw": (
            tmp_path / ".venv" / "Scripts" / "hive-mind-capture-hookw.exe"
        ).resolve(),
        "hive-mind-supervisorw": (
            tmp_path / ".venv" / "Scripts" / "hive-mind-supervisorw.exe"
        ).resolve(),
        "hive-mind-post-rebootw": (
            tmp_path / ".venv" / "Scripts" / "hive-mind-post-rebootw.exe"
        ).resolve(),
    }


def test_validate_gui_launchers_rejects_missing_executables(tmp_path: Path):
    with pytest.raises(RuntimeError, match="missing"):
        validate_gui_launchers(tmp_path)


def test_validate_gui_launchers_rejects_console_subsystem(tmp_path: Path):
    launchers = expected_gui_launchers(tmp_path)
    for executable in launchers.values():
        _write_pe(executable, 2)
    _write_pe(launchers["hive-mind-supervisorw"], 3)

    with pytest.raises(RuntimeError, match="Subsystem 2"):
        validate_gui_launchers(tmp_path)


def _install_probe_double(
    monkeypatch,
    *,
    prefix: Path,
    package_origin: Path,
    sys_executable: Path | None = None,
):
    calls: list[tuple[list[str], int]] = []

    def fake_run(command, **kwargs):
        probe_path = Path(command[-1])
        probe_path.write_text(
            json.dumps(
                {
                    "sys_prefix": str(prefix),
                    "package_origin": str(package_origin),
                    "sys_executable": str(sys_executable or Path(command[0])),
                }
            ),
            encoding="utf-8",
        )
        calls.append((list(command), kwargs.get("creationflags", 0)))
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(
        "hive_mind.install.windows_launchers.subprocess.run", fake_run
    )
    return calls


def test_validate_gui_launchers_rejects_prefix_outside_selected_venv(
    tmp_path: Path, monkeypatch
):
    for executable in expected_gui_launchers(tmp_path).values():
        _write_pe(executable, 2)
    _install_probe_double(
        monkeypatch,
        prefix=tmp_path / "other-venv",
        package_origin=tmp_path / "src" / "hive_mind" / "__init__.py",
    )

    with pytest.raises(RuntimeError, match="sys.prefix"):
        validate_gui_launchers(tmp_path)


def test_validate_gui_launchers_rejects_package_origin_outside_project(
    tmp_path: Path, monkeypatch
):
    for executable in expected_gui_launchers(tmp_path).values():
        _write_pe(executable, 2)
    _install_probe_double(
        monkeypatch,
        prefix=tmp_path / ".venv",
        package_origin=tmp_path.parent / "global" / "hive_mind" / "__init__.py",
    )

    with pytest.raises(RuntimeError, match="package origin"):
        validate_gui_launchers(tmp_path)


def test_validate_gui_launchers_rejects_package_origin_from_project_venv(
    tmp_path: Path, monkeypatch
):
    for executable in expected_gui_launchers(tmp_path).values():
        _write_pe(executable, 2)
    _install_probe_double(
        monkeypatch,
        prefix=tmp_path / ".venv",
        package_origin=(
            tmp_path / ".venv" / "Lib" / "site-packages" / "hive_mind" / "__init__.py"
        ),
    )

    with pytest.raises(RuntimeError, match="package origin"):
        validate_gui_launchers(tmp_path)


def test_validate_gui_launchers_rejects_global_python_executable(
    tmp_path: Path, monkeypatch
):
    for executable in expected_gui_launchers(tmp_path).values():
        _write_pe(executable, 2)
    _install_probe_double(
        monkeypatch,
        prefix=tmp_path / ".venv",
        package_origin=tmp_path / "src" / "hive_mind" / "__init__.py",
        sys_executable=tmp_path.parent / "global-python" / "python.exe",
    )

    with pytest.raises(RuntimeError, match="sys.executable"):
        validate_gui_launchers(tmp_path)


def test_validate_gui_launchers_rejects_console_pythonw_in_selected_venv(
    tmp_path: Path, monkeypatch
):
    for executable in expected_gui_launchers(tmp_path).values():
        _write_pe(executable, 2)
    interpreter = tmp_path / ".venv" / "Scripts" / "pythonw.exe"
    _write_pe(interpreter, 3)
    _install_probe_double(
        monkeypatch,
        prefix=tmp_path / ".venv",
        package_origin=tmp_path / "src" / "hive_mind" / "__init__.py",
        sys_executable=interpreter,
    )

    with pytest.raises(RuntimeError, match="interpreter must use PE Subsystem 2"):
        validate_gui_launchers(tmp_path)


def test_ensure_gui_pythonw_copies_gui_base_interpreter_into_project_venv(
    tmp_path: Path,
):
    base_prefix = tmp_path / ".uv" / "python" / "cpython-3.12"
    source = base_prefix / "pythonw.exe"
    _write_pe(source, 2)
    destination = tmp_path / ".venv" / "Scripts" / "pythonw.exe"
    _write_pe(destination, 3)

    ensured = ensure_gui_pythonw(tmp_path, base_prefix=base_prefix)

    assert ensured == destination.resolve()
    assert read_pe_subsystem(destination) == 2


def test_validate_gui_launchers_returns_evidence_from_no_window_file_probe(
    tmp_path: Path, monkeypatch
):
    launchers = expected_gui_launchers(tmp_path)
    for executable in launchers.values():
        _write_pe(executable, 2)
    calls = _install_probe_double(
        monkeypatch,
        prefix=tmp_path / ".venv",
        package_origin=tmp_path / "src" / "hive_mind" / "__init__.py",
    )

    evidence = validate_gui_launchers(tmp_path)

    assert {item.name for item in evidence} == set(launchers)
    assert all(item.subsystem == 2 for item in evidence)
    assert all(item.prefix == (tmp_path / ".venv").resolve() for item in evidence)
    assert all("--hive-mind-launcher-probe" in command for command, _ in calls)
    assert all(command[-1].endswith(".json") for command, _ in calls)
    assert all(flags != 0 for _, flags in calls)
