[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
$logDir = Join-Path $Root "logs\sync-diario"
Ensure-HiveMindDirectory -Path $logDir
$stamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$log = Join-Path $logDir "sync-$stamp.log"
$graph = Join-Path $Root "scripts\graph\build-graph.ps1"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $graph -Force *> $log
if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $log; exit $LASTEXITCODE }
Remove-HiveMindOldFiles -Path $logDir -Days 30 -Filter "*.log"
Write-Host $log
