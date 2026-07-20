"""Unit tests for runtime.yaml Pydantic v2 schema and validation (F2 / D006)."""
from __future__ import annotations

from pathlib import Path
import pytest
from pydantic import ValidationError

from hive_mind.daemon.manifest import (
    RuntimeManifest,
    ServiceSpec,
    load_manifest,
    validate_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_YAML = ROOT / "config" / "runtime.yaml"


def test_shipped_runtime_yaml_is_valid():
    assert RUNTIME_YAML.exists(), f"missing runtime.yaml at {RUNTIME_YAML}"
    manifest = load_manifest(RUNTIME_YAML)
    assert manifest.schema_version == 3
    assert len(manifest.services) >= 7
    assert len(manifest.external_services) >= 7
    assert len(manifest.jobs) >= 2


def test_duplicate_service_names_raises_validation_error():
    data = {
        "schema_version": 3,
        "services": [
            {"name": "service-a", "command": ["python"], "startup_order": 10},
            {"name": "service-a", "command": ["python"], "startup_order": 20},
        ],
    }
    with pytest.raises(ValidationError) as exc:
        RuntimeManifest.model_validate(data)
    assert "Nome de serviço duplicado" in str(exc.value)


def test_duplicate_startup_orders_raises_validation_error():
    data = {
        "schema_version": 3,
        "services": [
            {"name": "service-a", "command": ["python"], "startup_order": 10},
            {"name": "service-b", "command": ["python"], "startup_order": 10},
        ],
    }
    with pytest.raises(ValidationError) as exc:
        RuntimeManifest.model_validate(data)
    assert "startup_order duplicado" in str(exc.value)


def test_missing_dependency_raises_validation_error():
    data = {
        "schema_version": 3,
        "services": [
            {
                "name": "service-a",
                "command": ["python"],
                "startup_order": 10,
                "dependencies": ["non-existent-service"],
            }
        ],
    }
    with pytest.raises(ValidationError) as exc:
        RuntimeManifest.model_validate(data)
    assert "depende de 'non-existent-service' que não existe" in str(exc.value)


def test_validate_manifest_helper():
    assert validate_manifest(RUNTIME_YAML) == []
