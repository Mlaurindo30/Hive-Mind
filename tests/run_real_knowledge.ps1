[CmdletBinding()]
param(
    [string]$Report = "logs\real-knowledge-report.xml"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
Ensure-HiveMindDirectory -Path (Join-Path $Root "logs")
Invoke-HiveMindPython -Root $Root -Arguments @("-m", "pytest", "tests/real", "-m", "real", "-v", "--timeout=1200", "--junitxml", $Report)
