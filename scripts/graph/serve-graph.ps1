[CmdletBinding()]
param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
$graph = Join-Path $Root "cerebro\cortex\occipital\grafo\graph.json"
if (-not (Test-Path -LiteralPath $graph)) {
    throw "Graph not found at $graph. Run scripts\graph\build-graph.ps1 first."
}
Invoke-HiveMindPython -Root $Root -Arguments @("-m", "graphify.serve", "--graph", $graph, "--port", "$Port")
