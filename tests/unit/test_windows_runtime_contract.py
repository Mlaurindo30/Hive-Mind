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
    script_path.write_text(script, encoding="utf-8")
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
$module = Get-Module HiveMind.Windows
$marker = Join-Path $env:HIVEMIND_TEST_ROOT "repair-called"

& $module {
    function Test-HiveMindPythonRuntime { param([string]$Root) return $true }
    function Repair-HiveMindPythonRuntime { param([string]$Root) throw "valid runtime was repaired" }
    Ensure-HiveMindPythonRuntime -Root $env:HIVEMIND_TEST_ROOT
}

if (Test-Path -LiteralPath $marker) {
    throw "valid runtime invoked repair"
}

& $module {
    function Test-HiveMindPythonRuntime { param([string]$Root) return $false }
    function Repair-HiveMindPythonRuntime {
        param([string]$Root)
        Set-Content -LiteralPath (Join-Path $Root "repair-called") -Value "yes"
    }
    Ensure-HiveMindPythonRuntime -Root $env:HIVEMIND_TEST_ROOT
}

if (-not (Test-Path -LiteralPath $marker)) {
    throw "invalid runtime did not invoke repair"
}
''',
    )


def test_runtime_repair_invokes_uv_provisioning_commands(tmp_path):
    run_powershell(
        tmp_path,
        r'''
Import-Module $env:HIVEMIND_MODULE -Force -DisableNameChecking
$module = Get-Module HiveMind.Windows
$log = Join-Path $env:HIVEMIND_TEST_ROOT "uv.log"
$env:HIVEMIND_UV_LOG = $log

& $module {
    function uv {
        param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
        Add-Content -LiteralPath $env:HIVEMIND_UV_LOG -Value ($Arguments -join " ")
        cmd.exe /c exit 0
    }
    Repair-HiveMindPythonRuntime -Root $env:HIVEMIND_TEST_ROOT
}

$commands = @(Get-Content -LiteralPath $log)
$expectedVenv = "venv --python 3.12 --clear $(Join-Path $env:HIVEMIND_TEST_ROOT '.venv')"
if ($commands.Count -ne 2 -or $commands[0] -ne "python install 3.12" -or $commands[1] -ne $expectedVenv) {
    throw "Unexpected uv commands: $($commands -join '; ')"
}
''',
)
