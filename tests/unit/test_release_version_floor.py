from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "release" / "validate_package.py"


def load_module():
    spec = importlib.util.spec_from_file_location("release_validator", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_version_contract_rejects_a_downgrade_below_the_release_floor():
    validator = load_module()

    errors = validator.validate_versions(
        {
            "pyproject.toml": "3.9.0",
            "npm/package.json": "3.9.0",
            "core/version.py": "3.9.0",
        },
        minimum_version="3.10.0",
    )

    assert errors == ["release version 3.9.0 is below minimum 3.10.0"]
