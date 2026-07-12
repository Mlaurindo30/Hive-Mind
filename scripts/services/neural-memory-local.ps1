[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
$env:NEURAL_MEMORY_DIR = if ($env:NEURAL_MEMORY_DIR) { $env:NEURAL_MEMORY_DIR } else { Join-Path $Root "integrations\neural-memory\data" }
Ensure-HiveMindDirectory -Path $env:NEURAL_MEMORY_DIR
$extraArgs = @()
if ($null -ne $Arguments) {
    $extraArgs = @($Arguments | Where-Object { -not [string]::IsNullOrEmpty($_) })
}
Invoke-HiveMindPython -Root $Root -Arguments (@("scripts/services/mcp-lifecycle.py", "--name", "neural-memory", "--", "nmem-mcp") + $extraArgs)
