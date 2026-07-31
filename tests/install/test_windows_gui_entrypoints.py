from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from hive_mind.windows.entrypoints import (
    capture_hook_main,
    post_reboot_main,
    supervisor_main,
)


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "entrypoint", [supervisor_main, post_reboot_main, capture_hook_main]
)
def test_gui_entrypoint_probe_writes_explicit_json_without_starting_runtime(
    tmp_path: Path, monkeypatch, entrypoint
):
    output = tmp_path / "probe.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "hive-mind-gui-entrypoint",
            "--hive-mind-launcher-probe",
            str(output),
        ],
    )

    assert entrypoint() == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert Path(payload["sys_prefix"]).resolve() == Path(sys.prefix).resolve()
    assert Path(payload["package_origin"]).resolve().is_relative_to(ROOT)
    assert Path(payload["sys_executable"]).resolve() == Path(sys.executable).resolve()


def test_pyproject_declares_native_gui_scripts():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "[project.gui-scripts]" in pyproject
    assert (
        'hive-mind-supervisorw = "hive_mind.windows.entrypoints:supervisor_main"'
        in pyproject
    )
    assert (
        'hive-mind-post-rebootw = "hive_mind.windows.entrypoints:post_reboot_main"'
        in pyproject
    )
    assert (
        'hive-mind-capture-hookw = "hive_mind.windows.entrypoints:capture_hook_main"'
        in pyproject
    )


def test_windows_installer_validates_gui_launchers_immediately_after_sync():
    source = (ROOT / "src" / "hive_mind" / "install" / "windows.py").read_text(
        encoding="utf-8"
    )

    sync = source.index('["uv", "sync", "--frozen", "--all-groups"]')
    gui_interpreter = source.index("ensure_gui_pythonw(root)", sync)
    validation = source.index("validate_gui_launchers(root)", sync)
    wrappers = source.index('_step("Wrapper and UMC setup")', validation)
    agents = source.index('_step("MCP registration")', wrappers)
    tasks = source.index('_step("Scheduled knowledge jobs (Task Scheduler)")', agents)

    assert sync < gui_interpreter < validation < wrappers < agents < tasks
