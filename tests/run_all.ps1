[CmdletBinding()]
param(
    [switch]$SkipIntegration,
    [switch]$SkipE2E
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "tests\smoke\test_smoke.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Invoke-HiveMindPython -Root $Root -Arguments @("-m", "pytest", "tests/unit/", "-v")

if (-not $SkipIntegration) {
    Invoke-HiveMindPython -Root $Root -Arguments @("-m", "pytest", "tests/integration/", "-v")
}

if (-not $SkipE2E) {
    Invoke-HiveMindPython -Root $Root -Arguments @("-m", "pytest", "tests/e2e/", "-v")
}
