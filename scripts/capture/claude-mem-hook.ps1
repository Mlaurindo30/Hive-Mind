[CmdletBinding()]
param(
    [ValidateSet("hook", "ensure-worker", "version-check")]
    [string]$Mode = "hook",

    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$local = Join-Path $Root "scripts\services\claude-mem-local.ps1"
$extraArgs = @()
if ($null -ne $Arguments) {
    $extraArgs = @($Arguments | Where-Object { -not [string]::IsNullOrEmpty($_) })
}
if ($Mode -eq "ensure-worker") {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $local "start" @extraArgs
} elseif ($Mode -eq "version-check") {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $local "version-check" @extraArgs
} else {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $local "mcp-server" @extraArgs
}
exit $LASTEXITCODE
