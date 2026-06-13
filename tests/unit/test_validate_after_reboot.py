from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "validate_after_reboot", ROOT / "scripts" / "validate_after_reboot.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_listening_ports_extracts_loopback(monkeypatch):
    output = "\n".join(
        [
            "LISTEN 0 512 127.0.0.1:37700 0.0.0.0:*",
            "LISTEN 0 5 127.0.0.1:37701 0.0.0.0:*",
            "LISTEN 0 2048 127.0.0.1:37702 0.0.0.0:*",
        ]
    )

    class Result:
        stdout = output

    monkeypatch.setattr(MODULE, "run", lambda *args, **kwargs: Result())
    assert MODULE.listening_ports() == {
        "37700": "127.0.0.1:37700",
        "37701": "127.0.0.1:37701",
        "37702": "127.0.0.1:37702",
    }


def test_prepare_records_current_boot(monkeypatch, tmp_path):
    marker = tmp_path / "pre-reboot.json"
    monkeypatch.setattr(MODULE, "LOG_DIR", tmp_path)
    monkeypatch.setattr(MODULE, "MARKER", marker)
    monkeypatch.setattr(MODULE, "REPORT", tmp_path / "post-reboot.json")
    monkeypatch.setattr(MODULE, "boot_id", lambda: "boot-before")
    assert MODULE.prepare() == 0
    assert '"boot_id": "boot-before"' in marker.read_text()
