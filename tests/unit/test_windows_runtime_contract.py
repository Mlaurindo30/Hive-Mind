import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "lib" / "HiveMind.Windows.psm1"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


def run_powershell(tmp_path: Path, script: str) -> None:
    if POWERSHELL is None:
        pytest.skip("PowerShell is required to test the Windows runtime contract")

    script_path = tmp_path / "runtime-contract.ps1"
    script_path.write_text('$ErrorActionPreference = "Stop"\n' + script, encoding="utf-8")
    env = os.environ | {
        "HIVEMIND_MODULE": str(MODULE),
        "HIVEMIND_TEST_ROOT": str(tmp_path),
    }
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"PowerShell contract failed with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_vault_template_sync_restores_missing_files_without_overwrite(tmp_path):
    run_powershell(
        tmp_path,
        r'''
Import-Module $env:HIVEMIND_MODULE -Force -DisableNameChecking
$root = $env:HIVEMIND_TEST_ROOT
$template = Join-Path $root "templates\vault\tronco\modelos"
$existing = Join-Path $root "cerebro\tronco\modelos"
New-Item -ItemType Directory -Path $template -Force | Out-Null
New-Item -ItemType Directory -Path $existing -Force | Out-Null
Set-Content -LiteralPath (Join-Path $template "session-log.md") -Value "shipped session" -Encoding UTF8
Set-Content -LiteralPath (Join-Path $template "daily-log.md") -Value "shipped daily" -Encoding UTF8
Set-Content -LiteralPath (Join-Path $existing "session-log.md") -Value "user session" -Encoding UTF8
Sync-HiveMindVaultTemplates -Root $root
if ((Get-Content -LiteralPath (Join-Path $existing "session-log.md") -Raw).Trim() -ne "user session") {
    throw "existing template was overwritten"
}
if ((Get-Content -LiteralPath (Join-Path $existing "daily-log.md") -Raw).Trim() -ne "shipped daily") {
    throw "missing template was not materialized"
}
''',
    )

def test_runtime_version_accepts_only_python_312(tmp_path):
    run_powershell(
        tmp_path,
        r'''
Import-Module $env:HIVEMIND_MODULE -Force -DisableNameChecking
$cases = @(
    @{ Version = "Python 3.11.9"; Expected = $false },
    @{ Version = "Python 3.12.13"; Expected = $true },
    @{ Version = "Python 3.13.0"; Expected = $false }
)

foreach ($case in $cases) {
    $actual = Test-HiveMindPythonVersion -Version $case.Version
    if ($actual -ne $case.Expected) {
        throw "Unexpected result for $($case.Version): $actual"
    }
}
''',
    )


def test_runtime_repair_decision_skips_valid_and_repairs_invalid_runtime(tmp_path):
    run_powershell(
        tmp_path,
        r'''
Import-Module $env:HIVEMIND_MODULE -Force -DisableNameChecking
$source = Get-Content -LiteralPath $env:HIVEMIND_MODULE -Raw
if (-not $source.Contains('ensure-python-runtime')) {
    throw "Ensure-HiveMindPythonRuntime must delegate to the native Python owner"
}
if (-not $source.Contains('repair-python-runtime')) {
    throw "Repair-HiveMindPythonRuntime must delegate to the native Python owner"
}
''',
    )


def test_runtime_repair_invokes_uv_provisioning_commands(tmp_path):
    run_powershell(
        tmp_path,
        r'''
Import-Module $env:HIVEMIND_MODULE -Force -DisableNameChecking
$source = Get-Content -LiteralPath $env:HIVEMIND_MODULE -Raw
if ($source.Contains('& uv python install 3.12')) {
    throw "Repair-HiveMindPythonRuntime must not embed uv provisioning logic anymore"
}
if (-not $source.Contains('repair-python-runtime')) {
    throw "Repair-HiveMindPythonRuntime must delegate to the native Python owner"
}
''',
)
