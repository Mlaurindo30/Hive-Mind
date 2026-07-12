[CmdletBinding()]
param(
    [switch]$WithTests
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$local = Join-Path $Root "tests\install\run-clean-install-test-local.ps1"
$args = @()
if ($WithTests) { $args += "-WithTests" }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $local @args
exit $LASTEXITCODE
