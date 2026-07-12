[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Script = Join-Path $PSScriptRoot "services\claude-mem-local.ps1"
$extraArgs = @()
if ($null -ne $Arguments) {
    $extraArgs = @($Arguments | Where-Object { -not [string]::IsNullOrEmpty($_) })
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script @extraArgs
exit $LASTEXITCODE
