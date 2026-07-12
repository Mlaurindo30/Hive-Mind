[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$CodexOnly,
    [switch]$ClaudeOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking

$python = Get-HiveMindPython -Root $Root
$server = Join-Path $Root "scripts\services\sinapse-mcp.py"
$mcp = @{
    command = $python
    args = @($server)
    env = @{
        SINAPSE_HOME = $Root
    }
}

function ConvertTo-PlainHashtable {
    param([Parameter(Mandatory = $true)]$Value)

    if ($null -eq $Value) { return $null }
    if ($Value -is [System.Collections.IDictionary]) {
        $result = @{}
        foreach ($key in $Value.Keys) {
            $result[$key] = ConvertTo-PlainHashtable $Value[$key]
        }
        return $result
    }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        $items = @()
        foreach ($item in $Value) {
            $items += ConvertTo-PlainHashtable $item
        }
        return $items
    }
    if ($Value.PSObject.Properties.Count -gt 0 -and $Value -isnot [string]) {
        $result = @{}
        foreach ($prop in $Value.PSObject.Properties) {
            $result[$prop.Name] = ConvertTo-PlainHashtable $prop.Value
        }
        return $result
    }
    return $Value
}

function Merge-McpConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$ServerName
    )

    $dir = Split-Path -Parent $Path
    Ensure-HiveMindDirectory -Path $dir

    $json = @{}
    if (Test-Path -LiteralPath $Path) {
        try {
            $json = ConvertTo-PlainHashtable (Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json)
        } catch {
            Write-Warning "Invalid JSON in $Path; skipping this file."
            return
        }
    }

    if (-not $json.ContainsKey("mcpServers")) {
        $json["mcpServers"] = @{}
    }
    $json["mcpServers"][$ServerName] = $mcp

    if ($Check) {
        $status = if ((Test-Path -LiteralPath $Path) -and $json["mcpServers"].ContainsKey($ServerName)) { "configured" } else { "missing" }
        Write-Host "${Path}: $status"
        return
    }

    $json | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $Path -Encoding UTF8
    Write-Host "registered $ServerName in $Path"
}

if (-not $ClaudeOnly) {
    Merge-McpConfig -Path (Join-Path $Root ".mcp.json") -ServerName "sinapse-memory"
    Merge-McpConfig -Path (Join-Path $env:USERPROFILE ".codex\mcp.json") -ServerName "sinapse-memory"
}
if (-not $CodexOnly) {
    Merge-McpConfig -Path (Join-Path $env:USERPROFILE ".claude.json") -ServerName "sinapse-memory"
}

# Hive-Mind capture hooks (additive; a failure here must never block MCP
# registration — the hooks themselves are non-blocking by contract).
$captureHooksInstaller = Join-Path $Root "scripts\setup\install-capture-hooks.py"
if ((Test-Path -LiteralPath $captureHooksInstaller) -and (Test-Path -LiteralPath $python)) {
    $captureMode = if ($Check) { "--check" } else { "--install" }
    try {
        & $python $captureHooksInstaller $captureMode
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "install-capture-hooks.py $captureMode exited with $LASTEXITCODE"
        }
    } catch {
        Write-Warning "capture hook installation failed: $_"
    }
}
