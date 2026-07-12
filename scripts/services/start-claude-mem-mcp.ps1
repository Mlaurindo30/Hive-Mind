[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
$target = Join-Path $Root "scripts\services\claude-mem-local.ps1"
$extraArgs = @()
if ($null -ne $Arguments) {
    $extraArgs = @($Arguments | Where-Object { -not [string]::IsNullOrEmpty($_) })
}
Invoke-HiveMindPython -Root $Root -Arguments (@("scripts/services/mcp-lifecycle.py", "--name", "claude-mem", "--") + @("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $target, "mcp-server") + $extraArgs)
