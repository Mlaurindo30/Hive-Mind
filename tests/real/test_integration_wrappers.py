"""Real import/contract checks for K1 integration wrappers.

These tests intentionally use real installed SDKs and wrapper modules. They do
not mock network clients; offline services must be reported by wrapper health,
not hidden behind fake successes.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.real
def test_k1_sdk_imports_are_installed_in_real_venv():
    for module_name in ("pymilvus", "ragflow_sdk", "llama_index"):
        module = importlib.import_module(module_name)
        assert module is not None


@pytest.mark.real
def test_k1_wrapper_artifacts_exist_without_vendored_monorepos():
    for name in ("milvus", "ragflow"):
        root = PROJECT_ROOT / "integrations" / name
        assert (root / "client.py").is_file()
        assert (root / "docker-compose.yml").is_file()
        assert (root / "README.md").is_file()
        assert not (root / ".git").exists(), f"{name} deve ser wrapper, nao clone"


@pytest.mark.real
def test_k1_wrapper_compose_files_are_valid_and_digest_pinned():
    from scripts.setup.verify_wrappers import verify_all_wrappers

    reports = verify_all_wrappers(PROJECT_ROOT)
    assert {report["name"] for report in reports} == {"milvus", "ragflow"}
    for report in reports:
        assert report["ok"] is True, report
        assert report["image_has_digest"] is True, report
        assert report["compose_config_ok"] is True, report


@pytest.mark.real
def test_install_script_runs_wrapper_digest_verifier():
    install_script = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    assert "scripts/setup/verify_wrappers.py" in install_script


@pytest.mark.real
def test_integrations_update_runs_wrapper_digest_verifier():
    update_script = (PROJECT_ROOT / "scripts" / "maintenance" / "integrations-update.sh").read_text(encoding="utf-8")
    assert "scripts/setup/verify_wrappers.py" in update_script


@pytest.mark.real
def test_k1_wrappers_import_and_report_health_contracts():
    milvus = importlib.import_module("integrations.milvus.client")
    ragflow = importlib.import_module("integrations.ragflow.client")

    for module in (milvus, ragflow):
        health = module.assert_health(strict=False)
        assert set(("ok", "service", "endpoint")).issubset(health)
        assert isinstance(health["ok"], bool)
        assert health["service"] in {"milvus", "ragflow"}


@pytest.mark.real
def test_components_lock_keeps_external_services_out_of_git_components():
    import json

    lock = json.loads((PROJECT_ROOT / "config" / "components.lock.json").read_text())
    names = set(lock.get("components", lock).keys())
    assert not {"milvus", "ragflow", "llama_index", "llama-index"} & names
