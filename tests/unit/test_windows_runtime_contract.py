from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_installer_uses_uv_managed_python_312():
    source = (ROOT / "install.ps1").read_text(encoding="utf-8-sig")

    assert "uv python install 3.12" in source
    assert "uv venv --python 3.12" in source
    assert "& py -3.12 -m venv" not in source


def test_runtime_validation_executes_venv_python():
    source = (ROOT / "scripts/lib/HiveMind.Windows.psm1").read_text(
        encoding="utf-8-sig"
    )

    assert "function Test-HiveMindPythonRuntime" in source
    assert "--version" in source
