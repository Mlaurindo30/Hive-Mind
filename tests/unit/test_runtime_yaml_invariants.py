"""Unit tests for runtime.yaml invariants (F2 / D006)."""
from __future__ import annotations

from pathlib import Path
import pytest
from hive_mind.daemon.manifest import load_manifest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_YAML = ROOT / "config" / "runtime.yaml"


def test_runtime_yaml_service_categories_and_ownership():
    manifest = load_manifest(RUNTIME_YAML)
    service_map = {s.name: s for s in manifest.services}

    assert service_map["sinapse-claude-mem"].category == "background-service"
    assert service_map["sinapse-capture-realtime"].category == "user-session"
    assert all(s.ownership == "legacy" for s in manifest.services)


def test_runtime_yaml_startup_order_sequence():
    manifest = load_manifest(RUNTIME_YAML)
    orders = [s.startup_order for s in manifest.services]
    assert orders == sorted(orders), "startup_order deve estar em ordem estritamente crescente"


def test_external_services_readiness_probes_configured():
    manifest = load_manifest(RUNTIME_YAML)
    ext_map = {e.name: e for e in manifest.external_services}

    assert ext_map["ollama"].readiness.type == "http"
    assert ext_map["docker-desktop"].readiness.type == "command"
    assert ext_map["falkordb"].readiness.type == "tcp"
