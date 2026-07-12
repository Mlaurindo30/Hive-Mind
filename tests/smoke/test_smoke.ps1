[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking

$failed = $false
function Check {
    param([string]$Name, [scriptblock]$Probe)
    try {
        & $Probe | Out-Null
        Write-Host "[ok] $Name"
    } catch {
        Write-Warning "[fail] $Name - $($_.Exception.Message)"
        $script:failed = $true
    }
}

Check "python" { Get-HiveMindPython -Root $Root -AllowSystem }
Check "project root" { if (-not (Test-Path -LiteralPath (Join-Path $Root "pyproject.toml"))) { throw "missing pyproject.toml" } }
Check "env file" { if (-not (Test-Path -LiteralPath (Join-Path $Root ".env"))) { throw "missing .env" } }
Check "vault" { if (-not (Test-Path -LiteralPath (Join-Path $Root "cerebro"))) { throw "missing cerebro" } }
Check "UMC database" { if (-not (Test-Path -LiteralPath (Join-Path $Root "hive_mind.db"))) { throw "missing hive_mind.db" } }
Check "PowerShell script parity" {
    $missing = Get-ChildItem -LiteralPath $Root -Recurse -Filter "*.sh" |
        Where-Object { $_.FullName -notmatch "\\.venv\\" -and $_.FullName -notmatch "\\integrations\\(graphify|neural-memory|rtk)\\" } |
        ForEach-Object { [IO.Path]::ChangeExtension($_.FullName, ".ps1") } |
        Where-Object { -not (Test-Path -LiteralPath $_) }
    if ($missing) { throw ("missing ps1 peers: " + ($missing -join ", ")) }
}

if ($failed) { exit 1 }
Write-Host "smoke ok"
