import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "health" / "validate_after_reboot_windows.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_after_reboot_windows", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_required_service_assessment_ignores_optional_entries():
    module = load_module()
    healthy, unhealthy = module.assess_required_services(
        {
            "api": {"state": "healthy"},
            "optional-dashboard": {"state": "degraded"},
        },
        ["api"],
    )

    assert healthy is True
    assert unhealthy == []


def test_required_service_assessment_reports_missing_and_degraded_required_services():
    module = load_module()
    healthy, unhealthy = module.assess_required_services(
        {"api": {"state": "degraded"}},
        ["api", "mcp"],
    )

    assert healthy is False
    assert unhealthy == ["api", "mcp"]
