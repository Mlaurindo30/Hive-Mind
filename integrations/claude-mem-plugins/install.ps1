[CmdletBinding()]
param(
    [string]$Target = (Join-Path $env:USERPROFILE ".gemini\antigravity-cli\plugins\claude-mem")
)

$ErrorActionPreference = "Stop"
$Source = $PSScriptRoot
if (-not (Test-Path -LiteralPath $Source)) {
    throw "Plugin source not found: $Source"
}
New-Item -ItemType Directory -Path $Target -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $Source "*") -Destination $Target -Recurse -Force
Write-Host "claude-mem plugin installed to $Target"
