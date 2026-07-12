[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
$logDir = Join-Path $Root "logs\backup-audit"
Ensure-HiveMindDirectory -Path $logDir
$stamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$out = Join-Path $logDir "audit-$stamp.json"
$python = Get-HiveMindPython -Root $Root
& $python (Join-Path $Root "scripts\health\backup_audit.py") "--json" | Set-Content -LiteralPath $out -Encoding UTF8
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Remove-HiveMindOldFiles -Path $logDir -Days 60 -Filter "*.json"
Write-Host $out
