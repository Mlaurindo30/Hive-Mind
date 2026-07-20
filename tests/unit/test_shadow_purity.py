"""D007 — shadow mode is absolutely passive (spec Anexo D.4).

A daemon in shadow ownership MUST NOT:
  - start child processes (no subprocess.Popen / os.system / os.spawn*);
  - write to runtime.yaml;
  - create any state file other than services.shadow.json;
  - trigger jobs or perform a cutover.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hive_mind.daemon.manifest import RuntimeManifest
from hive_mind.daemon.supervisor import ShadowSupervisor


def _manifest() -> RuntimeManifest:
    return RuntimeManifest.model_validate(
        {
            "schema_version": 3,
            "profile": "local-min",
            "services": [
                {
                    "name": "svc",
                    "command": ["would-run-this"],
                    "startup_order": 1,
                    "readiness": {"type": "tcp", "host": "127.0.0.1", "port": 5432},
                }
            ],
        }
    )


def test_observe_never_spawns_a_process(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("shadow mode must not spawn processes")

    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "call", explode)

    supervisor = ShadowSupervisor(_manifest(), state_dir=tmp_path)
    supervisor.observe(prober=lambda spec: True)  # must not raise


def test_observe_does_not_touch_runtime_yaml(tmp_path):
    runtime_yaml = tmp_path / "runtime.yaml"
    original = "schema_version: 3\nprofile: local-min\n"
    runtime_yaml.write_text(original, encoding="utf-8")
    before = runtime_yaml.stat().st_mtime_ns

    ShadowSupervisor(_manifest(), state_dir=tmp_path).observe(prober=lambda s: True)

    assert runtime_yaml.read_text(encoding="utf-8") == original
    assert runtime_yaml.stat().st_mtime_ns == before


def test_observe_creates_only_shadow_state_file(tmp_path):
    ShadowSupervisor(_manifest(), state_dir=tmp_path).observe(prober=lambda s: True)
    created = {p.name for p in tmp_path.iterdir()}
    assert created == {"services.shadow.json"}


def test_supervisor_exposes_its_shadow_ownership(tmp_path):
    supervisor = ShadowSupervisor(_manifest(), state_dir=tmp_path)
    assert supervisor.ownership == "shadow"


def test_repeated_observation_is_idempotent_on_the_filesystem(tmp_path):
    supervisor = ShadowSupervisor(_manifest(), state_dir=tmp_path)
    supervisor.observe(prober=lambda s: True)
    supervisor.observe(prober=lambda s: True)
    created = {p.name for p in tmp_path.iterdir()}
    assert created == {"services.shadow.json"}
