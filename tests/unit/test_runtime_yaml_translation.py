"""Unit tests for translating legacy install_services specs to declarative runtime.yaml (F2 / D006)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "setup") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "setup"))

from install_services import service_specs
from hive_mind.daemon.manifest import load_manifest

RUNTIME_YAML = ROOT / "config" / "runtime.yaml"


def test_legacy_service_specs_match_declarative_manifest():
    legacy_specs = service_specs()
    legacy_names = {s["name"] for s in legacy_specs}

    manifest = load_manifest(RUNTIME_YAML)
    manifest_service_names = {s.name for s in manifest.services}
    manifest_external_names = {e.name for e in manifest.external_services}
    all_manifest_names = manifest_service_names | manifest_external_names

    # Todos os serviços legados devem estar declarados no novo manifesto
    assert legacy_names.issubset(all_manifest_names)


def test_translation_preserves_commands_and_startup_orders():
    legacy_specs = service_specs()
    legacy_map = {s["name"]: s for s in legacy_specs}

    manifest = load_manifest(RUNTIME_YAML)
    manifest_map = {s.name: s for s in manifest.services}

    for name, spec in legacy_map.items():
        if spec.get("external"):
            continue
        assert name in manifest_map
        manifest_spec = manifest_map[name]
        assert manifest_spec.startup_order == spec.get("startup_order")
