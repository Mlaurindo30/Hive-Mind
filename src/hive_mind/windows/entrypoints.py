"""Console-free Windows entry points installed through PEP 621 GUI scripts."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


_PROBE_ARGUMENT = "--hive-mind-launcher-probe"


def _ensure_standard_streams() -> None:
    """Give GUI launchers writable sinks when Windows supplies no console."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _write_probe_if_requested(arguments: list[str]) -> bool:
    if not arguments or arguments[0] != _PROBE_ARGUMENT:
        return False
    if len(arguments) != 2:
        raise SystemExit(f"{_PROBE_ARGUMENT} requires one JSON output path")

    import hive_mind

    package_origin = getattr(hive_mind, "__file__", None)
    if not package_origin:
        raise SystemExit("hive_mind package origin is unavailable")
    output = Path(arguments[1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sys_prefix": str(Path(sys.prefix).resolve()),
        "package_origin": str(Path(package_origin).resolve()),
        "sys_executable": str(Path(sys.executable).resolve()),
    }
    output.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return True


def supervisor_main() -> int:
    _ensure_standard_streams()
    arguments = sys.argv[1:]
    if _write_probe_if_requested(arguments):
        return 0

    from hive_mind.daemon.main import main as daemon_main

    if arguments and arguments[0] == "run":
        return daemon_main(arguments)
    return daemon_main(["run", "--serve", *arguments])


def post_reboot_main() -> int:
    _ensure_standard_streams()
    arguments = sys.argv[1:]
    if _write_probe_if_requested(arguments):
        return 0
    if arguments:
        raise SystemExit("hive-mind-post-rebootw does not accept runtime arguments yet")

    from hive_mind.project import resolve_project_root

    root = resolve_project_root()
    script = root / "scripts" / "health" / "validate_after_reboot_windows.py"
    if not script.is_file():
        raise SystemExit(f"post-reboot validator was not found: {script}")
    spec = importlib.util.spec_from_file_location(
        "_hive_mind_post_reboot_compat", script
    )
    if spec is None or spec.loader is None:
        raise SystemExit(f"post-reboot validator could not be loaded: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main())


def capture_hook_main() -> int:
    _ensure_standard_streams()
    arguments = sys.argv[1:]
    if _write_probe_if_requested(arguments):
        return 0

    from hive_mind.project import resolve_project_root

    root = resolve_project_root()
    script = root / "scripts" / "capture" / "capture-hook.py"
    if not script.is_file():
        raise SystemExit(f"capture hook was not found: {script}")
    spec = importlib.util.spec_from_file_location(
        "_hive_mind_capture_hook_compat", script
    )
    if spec is None or spec.loader is None:
        raise SystemExit(f"capture hook could not be loaded: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main(arguments))
