[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Extract,
    [switch]$SkipHnsw
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking
Set-Location -LiteralPath $Root
Import-HiveMindDotEnv -Root $Root | Out-Null

$vault = Join-Path $Root "cerebro"
if (-not (Test-Path -LiteralPath $vault)) {
    throw "Vault not found at $vault"
}
$graphOut = Join-Path $vault "cortex\occipital\grafo"
Ensure-HiveMindDirectory -Path $graphOut
$env:GRAPHIFY_OUT = $graphOut

$graphify = Join-Path (Get-HiveMindVenvScripts -Root $Root) "graphify.exe"
if (-not (Test-Path -LiteralPath $graphify)) {
    $graphify = "graphify"
}

$graph = Join-Path $graphOut "graph.json"
if (Test-Path -LiteralPath $graph) {
    Copy-Item -LiteralPath $graph -Destination (Join-Path $graphOut "graph.json.bak") -Force
}

$args = @("update", $vault)
if ($Force) { $args += "--force" }
& $graphify @args
if ($LASTEXITCODE -ne 0) {
    if (-not (Test-Path -LiteralPath $graph)) {
        Write-Warning "Graphify did not build a graph, probably because the vault has no code files yet. Creating an empty graph.json."
        [IO.File]::WriteAllText($graph, '{"nodes":[],"links":[]}', (New-Object Text.UTF8Encoding $false))
    } else {
        Write-Warning "Graphify did not rebuild the graph. Keeping existing graph.json and validating it."
    }
}

if ($Extract) {
    & $graphify "extract" $vault "--out" $graphOut
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not $SkipHnsw) {
    Invoke-HiveMindPython -Root $Root -Arguments @("-c", "from core.hnsw_index import incremental_update; from core.database import embed_text, get_connection; conn=get_connection(); n=incremental_update(conn, embed_text); conn.close(); print(f'HNSW: {n} neurons indexed')")
}

Invoke-HiveMindPython -Root $Root -Arguments @("-c", "import json, pathlib; p=pathlib.Path(r'$graph'); json.loads(p.read_text(encoding='utf-8-sig')); print('graph ok:', p)")
