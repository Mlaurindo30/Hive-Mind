[CmdletBinding()]
param([string]$Root = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))
$ErrorActionPreference='Stop'
$env:HIVE_MIND_HOME=$Root
$node=Get-Command node.exe -ErrorAction Stop
& $node.Source (Join-Path $Root 'npm\lib\supervisor.js') __daemon
exit $LASTEXITCODE