[CmdletBinding()]
param(
    [ValidateSet("backup", "verify", "rebuild-indexes", "restore")]
    [string]$Action = "verify",

    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
$extraArgs = @()
if ($null -ne $Arguments) {
    $extraArgs = @($Arguments | Where-Object { -not [string]::IsNullOrEmpty($_) })
}
Invoke-HiveMindPython -Root $Root -Arguments (@("scripts/utils/recovery.py", $Action) + $extraArgs)
