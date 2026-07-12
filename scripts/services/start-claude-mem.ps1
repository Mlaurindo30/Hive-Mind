[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Script = Join-Path $PSScriptRoot "start-claude-mem-mcp.ps1"
$extraArgs = @()
if ($null -ne $Arguments) {
    $extraArgs = @($Arguments | Where-Object { -not [string]::IsNullOrEmpty($_) })
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script @extraArgs
exit $LASTEXITCODE
