"""Tests for the HiveMind-Backup scheduled-job wrapper.

The wrapper at ``scripts/maintenance/backup.py`` is the Python target
referenced by ``register-windows-jobs.ps1`` (task ``HiveMind-Backup``). It
delegates to ``scripts/health/backup_audit.py`` and writes a per-execution
log artifact under ``logs/backup/``. These tests assert:

* The wrapper can be imported and exposes ``main`` / ``parse_args``.
* The default mode is read-only (``--apply`` not implied).
* The audit report is produced and a log file is written.
* ``--apply`` triggers ``backup_audit.apply_prune``.
* ``--json`` emits machine-readable JSON to stdout.
"""

from __future__ import annotations

import importlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _load_wrapper():
    sys.path.insert(0, str(REPO))
    if "scripts.maintenance.backup" in sys.modules:
        return sys.modules["scripts.maintenance.backup"]
    return importlib.import_module("scripts.maintenance.backup")


def test_wrapper_imports_and_exposes_entrypoint():
    wrapper = _load_wrapper()
    assert callable(wrapper.main)
    assert callable(wrapper.parse_args)
    assert wrapper._REPO_ROOT == REPO


def test_wrapper_default_is_read_only(tmp_path, monkeypatch):
    wrapper = _load_wrapper()
    log_dir = tmp_path / "logs" / "backup"
    monkeypatch.setattr(wrapper, "_REPO_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(wrapper.backup_audit, "run_audit", lambda root, args: {"directory_stats": {}, "stale_candidates": {}, "secret_hits": []})
    monkeypatch.setattr(wrapper.backup_audit, "apply_prune", lambda report: ["X"])
    monkeypatch.setattr(sys, "argv", [
        "backup.py", "--root", str(tmp_path), "--log-dir", str(log_dir),
    ])

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = wrapper.main()

    assert rc == 0
    files = list(log_dir.glob("backup-*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["applied"] is False
    assert payload.get("removed") is None


def test_wrapper_apply_invokes_prune(tmp_path, monkeypatch):
    wrapper = _load_wrapper()
    log_dir = tmp_path / "logs" / "backup"
    called = {"prune": 0, "report": 0}

    def fake_run_audit(root, args):
        called["report"] += 1
        assert args.apply is True
        return {"directory_stats": {}, "stale_candidates": {}, "secret_hits": [], "stale": ["x"]}

    def fake_apply_prune(report):
        called["prune"] += 1
        return [str(report["stale"][0])]

    monkeypatch.setattr(wrapper.backup_audit, "run_audit", fake_run_audit)
    monkeypatch.setattr(wrapper.backup_audit, "apply_prune", fake_apply_prune)
    monkeypatch.setattr(sys, "argv", [
        "backup.py", "--root", str(tmp_path), "--log-dir", str(log_dir), "--apply",
    ])

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = wrapper.main()

    assert rc == 0
    assert called["prune"] == 1
    assert called["report"] == 1
    payload = json.loads(list(log_dir.glob("backup-*.json"))[0].read_text(encoding="utf-8"))
    assert payload["applied"] is True
    assert payload["removed"] == ["x"]


def test_wrapper_json_output(tmp_path, monkeypatch):
    wrapper = _load_wrapper()
    log_dir = tmp_path / "logs" / "backup"
    monkeypatch.setattr(wrapper.backup_audit, "run_audit", lambda root, args: {"directory_stats": {}, "stale_candidates": {}, "secret_hits": [], "hello": "world"})
    monkeypatch.setattr(wrapper.backup_audit, "apply_prune", lambda report: [])
    monkeypatch.setattr(sys, "argv", [
        "backup.py", "--root", str(tmp_path), "--log-dir", str(log_dir), "--json",
    ])

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = wrapper.main()

    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["hello"] == "world"
    assert payload["applied"] is False


def test_wrapper_run_against_real_repo_read_only(tmp_path, monkeypatch):
    """Smoke-test the wrapper against the actual repo, read-only."""
    wrapper = _load_wrapper()
    log_dir = tmp_path / "logs" / "backup"
    import io as _io
    from contextlib import redirect_stdout as _rfo
    monkeypatch.setattr(sys, "argv", ["backup.py", "--root", str(REPO), "--log-dir", str(log_dir)])
    buf = _io.StringIO()
    with _rfo(buf):
        rc = wrapper.main()
    assert rc == 0
    # The wrapper writes a log file; verify at least one exists.
    logs = sorted(log_dir.glob("backup-*.json"))
    assert logs, "wrapper did not produce a log artifact"
    last = json.loads(logs[-1].read_text(encoding="utf-8"))
    assert "stale_candidates" in last
    assert last["applied"] is False





