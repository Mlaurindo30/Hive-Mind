[CmdletBinding()]
param(
    [switch]$WithTests
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$install = Join-Path $Root "install.ps1"
$args = @("-NonInteractive")
if ($WithTests) { $args += "-WithTests" }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $install @args
exit $LASTEXITCODE
