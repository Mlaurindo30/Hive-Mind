[CmdletBinding()]
param(
    [string]$Only,
    [switch]$All,
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
$rtk = Join-Path $Root "integrations\rtk\target\release\rtk.exe"
if (-not (Test-Path -LiteralPath $rtk)) {
    $cmd = Get-Command rtk -ErrorAction SilentlyContinue
    if ($cmd) { $rtk = $cmd.Source } else { throw "rtk was not found. Run install.ps1 after integrations are bootstrapped." }
}

$rtkArgs = @("init")
if ($All) {
    $rtkArgs += "--all"
} elseif ($Only) {
    $rtkArgs += @("--only", $Only)
}
$extraArgs = @()
if ($null -ne $Arguments) {
    $extraArgs = @($Arguments | Where-Object { -not [string]::IsNullOrEmpty($_) })
}
$rtkArgs += $extraArgs
& $rtk @rtkArgs
exit $LASTEXITCODE
