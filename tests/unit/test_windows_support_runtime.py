from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from hive_mind.install.windows_support import (
    project_python_home_is_local,
    project_uv_environment,
    repair_python_runtime,
)


def test_project_uv_environment_keeps_cache_and_managed_python_under_root(
    tmp_path: Path,
):
    environment = project_uv_environment(tmp_path)

    assert environment["UV_CACHE_DIR"] == str((tmp_path / ".uv" / "cache").resolve())
    assert environment["UV_PYTHON_INSTALL_DIR"] == str(
        (tmp_path / ".uv" / "python").resolve()
    )


def test_project_python_home_rejects_venv_backed_by_user_uv_runtime(
    tmp_path: Path,
):
    config = tmp_path / ".venv" / "pyvenv.cfg"
    config.parent.mkdir(parents=True)
    config.write_text(
        "home = C:\\Users\\miche\\AppData\\Roaming\\uv\\python\\cpython-3.12\n",
        encoding="utf-8",
    )

    assert not project_python_home_is_local(tmp_path)


def test_project_python_home_accepts_runtime_under_install_root(tmp_path: Path):
    config = tmp_path / ".venv" / "pyvenv.cfg"
    config.parent.mkdir(parents=True)
    config.write_text(
        f"home = {tmp_path / '.uv' / 'python' / 'cpython-3.12'}\n",
        encoding="utf-8",
    )

    assert project_python_home_is_local(tmp_path)


def test_repair_python_runtime_uses_project_uv_environment(
    tmp_path: Path, monkeypatch
):
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(command, **kwargs):
        calls.append((list(command), kwargs["env"]))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "hive_mind.install.windows_support.subprocess.run", fake_run
    )

    repair_python_runtime(tmp_path)

    expected = project_uv_environment(tmp_path)
    assert [call[0][:3] for call in calls] == [
        ["uv", "python", "install"],
        ["uv", "venv", "--python"],
    ]
    assert all(call[1]["UV_CACHE_DIR"] == expected["UV_CACHE_DIR"] for call in calls)
    assert all(
        call[1]["UV_PYTHON_INSTALL_DIR"] == expected["UV_PYTHON_INSTALL_DIR"]
        for call in calls
    )
