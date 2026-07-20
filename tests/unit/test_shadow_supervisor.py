"""D007 — ShadowSupervisor observes the manifest without acting (spec F3)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hive_mind.daemon.manifest import RuntimeManifest
from hive_mind.daemon.supervisor import ShadowSupervisor


def _manifest(**overrides) -> RuntimeManifest:
    data = {
        "schema_version": 3,
        "profile": "local-min",
        "services": [
            {
                "name": "db",
                "command": ["run-db"],
                "startup_order": 10,
                "required": True,
                "readiness": {"type": "tcp", "host": "127.0.0.1", "port": 5432},
            },
            {
                "name": "api",
                "command": ["run-api"],
                "startup_order": 20,
                "dependencies": ["db"],
                "readiness": {"type": "tcp", "host": "127.0.0.1", "port": 8080},
            },
        ],
    }
    data.update(overrides)
    return RuntimeManifest.model_validate(data)


def test_observe_writes_only_shadow_state(tmp_path):
    supervisor = ShadowSupervisor(_manifest(), state_dir=tmp_path)
    summary = supervisor.observe(prober=lambda spec: True)

    files = {p.name for p in tmp_path.iterdir()}
    assert files == {"services.shadow.json"}
    assert summary["mode"] == "shadow"
    assert summary["service_count"] == 2


def test_shadow_state_is_valid_json_with_per_service_records(tmp_path):
    supervisor = ShadowSupervisor(_manifest(), state_dir=tmp_path)
    supervisor.observe(prober=lambda spec: True)

    state = json.loads((tmp_path / "services.shadow.json").read_text(encoding="utf-8"))
    assert state["mode"] == "shadow"
    services = {s["name"]: s for s in state["services"]}
    assert services["db"]["required"] is True
    assert services["db"]["readiness"] == "ready"
    assert services["api"]["dependencies"] == ["db"]


def test_services_are_ordered_by_startup_order(tmp_path):
    manifest = _manifest()
    supervisor = ShadowSupervisor(manifest, state_dir=tmp_path)
    summary = supervisor.observe(prober=lambda spec: True)
    assert [s["name"] for s in summary["services"]] == ["db", "api"]


def test_readiness_unknown_without_a_prober(tmp_path):
    supervisor = ShadowSupervisor(_manifest(), state_dir=tmp_path)
    summary = supervisor.observe()  # no prober
    for service in summary["services"]:
        assert service["readiness"] == "unknown"


def test_not_ready_probe_is_recorded(tmp_path):
    supervisor = ShadowSupervisor(_manifest(), state_dir=tmp_path)
    summary = supervisor.observe(prober=lambda spec: False)
    for service in summary["services"]:
        assert service["readiness"] == "not_ready"


def test_ready_reports_required_satisfied_only_when_required_are_ready(tmp_path):
    manifest = _manifest()
    supervisor = ShadowSupervisor(manifest, state_dir=tmp_path)

    ready = supervisor.observe(prober=lambda spec: True)
    assert ready["ready"] is True  # required db is ready

    def db_down(spec) -> bool:
        return spec.name != "db"

    not_ready = supervisor.observe(prober=db_down)
    assert not_ready["ready"] is False  # required db down -> not ready


def test_only_active_profile_services_are_observed(tmp_path):
    manifest = _manifest(
        profile="local-min",
        services=[
            {"name": "always", "command": ["x"], "startup_order": 1},
            {
                "name": "fullonly",
                "command": ["y"],
                "startup_order": 2,
                "profiles": ["local-full"],
            },
        ],
    )
    supervisor = ShadowSupervisor(manifest, state_dir=tmp_path)
    summary = supervisor.observe(prober=lambda spec: True)
    assert [s["name"] for s in summary["services"]] == ["always"]


def test_disabled_services_are_skipped(tmp_path):
    manifest = _manifest(
        services=[
            {"name": "on", "command": ["x"], "startup_order": 1},
            {"name": "off", "command": ["y"], "startup_order": 2, "enabled": False},
        ]
    )
    supervisor = ShadowSupervisor(manifest, state_dir=tmp_path)
    summary = supervisor.observe(prober=lambda spec: True)
    assert [s["name"] for s in summary["services"]] == ["on"]
