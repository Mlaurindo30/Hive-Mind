[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
Import-HiveMindDotEnv -Root $Root | Out-Null
$env:SINAPSE_HOME = $Root
$env:PYTHONUNBUFFERED = "1"
$env:GRAPHIFY_OUT = Join-Path $Root "cerebro\\cortex\\occipital\\grafo"
if (-not $env:GRAPHIFY_WATCH_DEBOUNCE) { $env:GRAPHIFY_WATCH_DEBOUNCE = "30.0" }
$extraArgs = @()
if ($null -ne $Arguments) {
    $extraArgs = @($Arguments | Where-Object { -not [string]::IsNullOrEmpty($_) })
}
Invoke-HiveMindPython -Root $Root -Arguments (@("-m", "graphify", "watch", (Join-Path $Root "cerebro")) + $extraArgs)
