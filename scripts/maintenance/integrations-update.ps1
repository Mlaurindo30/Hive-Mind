[CmdletBinding()]
param(
    [switch]$SkipUv,
    [switch]$SkipClaudePlugin
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
Invoke-HiveMindPython -Root $Root -AllowSystem -Arguments @("scripts/setup/components.py", "update")
Invoke-HiveMindPython -Root $Root -AllowSystem -Arguments @("scripts/setup/components.py", "verify")
if (-not $SkipUv) {
    if (-not (Test-HiveMindCommand uv)) { throw "uv not found" }
    Push-Location -LiteralPath $Root
    try {
        & uv lock --upgrade
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & uv sync --frozen --all-groups
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}
Invoke-HiveMindPython -Root $Root -Arguments @("scripts/setup/verify_wrappers.py")
if (-not $SkipClaudePlugin -and (Test-HiveMindCommand claude)) {
    & claude plugins update claude-mem@thedotmack
}
