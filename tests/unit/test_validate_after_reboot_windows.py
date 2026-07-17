"""Regression tests for the Windows post-reboot validator."""
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "health" / "validate_after_reboot_windows.py"
SPEC = importlib.util.spec_from_file_location("validate_after_reboot_windows", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_installation_profile_reads_utf8_env_on_windows(tmp_path):
    (tmp_path / ".env").write_bytes(
        b"HIVE_MIND_PROFILE=local-full\nNOTE=\x9d\n"
    )

    assert MODULE.installation_profile(tmp_path) == "local-full"
