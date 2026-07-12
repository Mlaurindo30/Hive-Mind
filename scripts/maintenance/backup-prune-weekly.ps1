[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
$logDir = Join-Path $Root "logs\backup-prune"
Ensure-HiveMindDirectory -Path $logDir
$stamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$out = Join-Path $logDir "prune-$stamp.json"
$args = @("scripts/health/backup_audit.py", "--json")
if (-not $DryRun) { $args += "--apply" }
$python = Get-HiveMindPython -Root $Root
& $python @args | Set-Content -LiteralPath $out -Encoding UTF8
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Remove-HiveMindOldFiles -Path $logDir -Days 182 -Filter "*.json"
Write-Host $out
