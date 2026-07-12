[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
if (-not (Test-HiveMindCommand copilot)) {
    throw "copilot CLI was not found."
}
$env:SINAPSE_HOME = $Root
$extraArgs = @()
if ($null -ne $Arguments) {
    $extraArgs = @($Arguments | Where-Object { -not [string]::IsNullOrEmpty($_) })
}
& copilot @extraArgs
exit $LASTEXITCODE
