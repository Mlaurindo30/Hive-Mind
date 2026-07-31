"""D007 — `hive-mindd run --shadow` wires lock + supervisor passively."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hive_mind.daemon.main import main
from hive_mind.daemon import lock as daemon_lock

MANIFEST = """\
schema_version: 3
profile: local-min
services:
  - name: svc-a
    command: [run-a]
    startup_order: 1
    required: false
"""


def _write_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "runtime.yaml"
    path.write_text(MANIFEST, encoding="utf-8")
    return path


class _NoopLock:
    def __init__(self, state_dir):
        self.state_dir = state_dir

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


@pytest.fixture(autouse=True)
def _isolate_host_lock(monkeypatch):
    monkeypatch.setattr(daemon_lock, "SingleInstanceLock", _NoopLock)


def test_run_shadow_exits_zero_and_writes_state(tmp_path, capsys):
    manifest = _write_manifest(tmp_path)
    state_dir = tmp_path / "state"

    code = main(
        ["run", "--shadow", "--manifest", str(manifest), "--state-dir", str(state_dir)]
    )

    assert code == 0
    shadow = state_dir / "services.shadow.json"
    assert shadow.exists()
    state = json.loads(shadow.read_text(encoding="utf-8"))
    assert state["mode"] == "shadow"
    assert [s["name"] for s in state["services"]] == ["svc-a"]
    assert "shadow" in capsys.readouterr().out


def test_run_shadow_releases_lock_so_a_second_pass_succeeds(tmp_path):
    manifest = _write_manifest(tmp_path)
    state_dir = tmp_path / "state"
    args = ["run", "--shadow", "--manifest", str(manifest), "--state-dir", str(state_dir)]
    assert main(args) == 0
    assert main(args) == 0  # lock was released after the first pass


def test_run_shadow_missing_manifest_is_unavailable(tmp_path, capsys):
    code = main(
        [
            "run",
            "--shadow",
            "--manifest",
            str(tmp_path / "nope.yaml"),
            "--state-dir",
            str(tmp_path / "state"),
        ]
    )
    assert code == 69  # EX_UNAVAILABLE
    assert "state" not in {p.name for p in tmp_path.iterdir()} or not (
        tmp_path / "state" / "services.shadow.json"
    ).exists()


def test_bare_run_managed_is_still_unavailable(capsys):
    assert main(["run"]) == 69
    assert "not implemented" in capsys.readouterr().err
