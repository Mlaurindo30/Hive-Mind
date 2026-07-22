"""Regression tests for the Windows post-reboot validator."""
from __future__ import annotations

import importlib.util
import json
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


def test_main_fails_and_records_runtime_path_findings(tmp_path, monkeypatch):
    report_path = tmp_path / "post-reboot-validation.json"
    finding = {
        "source": "process:42:command_line",
        "value": r"D:\Hive-Mind-Archive\worker.py",
        "normalized_value": "d:/hive-mind-archive/worker.py",
        "reason": "forbidden_path_family",
        "matched": "hive-mind-archive",
    }
    monkeypatch.setattr(MODULE, "REPORT", report_path)
    monkeypatch.setattr(MODULE, "load_state", lambda: {"worker": {"state": "healthy"}})
    monkeypatch.setattr(
        MODULE,
        "load_manifest",
        lambda: {
            "services": [
                {
                    "name": "worker",
                    "required": True,
                    "enabled_profiles": ["local-min"],
                }
            ]
        },
    )
    monkeypatch.setattr(MODULE, "installation_profile", lambda: "local-min")
    monkeypatch.setattr(MODULE, "task_exists", lambda _name: True)
    monkeypatch.setattr(MODULE, "audit_runtime_paths", lambda _root: [finding])

    assert MODULE.main() == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["checks"]["canonical_runtime_paths"] is False
    assert report["runtime_path_findings"] == [finding]
    assert report["status"] == "fail"
