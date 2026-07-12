[CmdletBinding()]
param(
    [ValidateSet("start", "mcp-server", "worker", "version-check")]
    [string]$Mode = "start",

    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyString()]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking

function Find-ClaudeMemPlugin {
    $userHome = $env:USERPROFILE
    $cacheRoot = Join-Path $userHome ".claude\plugins\cache\thedotmack\claude-mem"
    $cacheCandidates = @()
    if (Test-Path -LiteralPath $cacheRoot) {
        $cacheCandidates = @(Get-ChildItem -LiteralPath $cacheRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            Select-Object -ExpandProperty FullName)
    }

    $candidates = @(
        $cacheCandidates
        (Join-Path $userHome ".claude\plugins\marketplaces\thedotmack")
        (Join-Path $userHome ".claude\plugins\marketplaces\thedotmack\plugin")
        (Join-Path $userHome ".codex\plugins\cache\thedotmack\claude-mem")
    )
    foreach ($candidate in ($candidates | ForEach-Object { $_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
        if (-not (Test-Path -LiteralPath $candidate)) { continue }
        foreach ($base in @($candidate, (Join-Path $candidate "scripts"), (Join-Path $candidate "plugin\scripts"))) {
            foreach ($entrypoint in @("worker-wrapper.cjs", "worker-wrapper.js", "worker-service.cjs", "worker-service.js")) {
                if (Test-Path -LiteralPath (Join-Path $base $entrypoint)) {
                    return $candidate
                }
            }
        }
    }
    return $null
}

$plugin = Find-ClaudeMemPlugin
if (-not $plugin) {
    throw "claude-mem plugin not found under .claude or .codex plugin caches."
}

function Find-Bun {
    $cmd = Get-Command bun -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $candidate = Get-ChildItem -LiteralPath $wingetRoot -Recurse -Filter "bun.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if ($candidate) { return $candidate }

    return $null
}

$bun = Find-Bun
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $bun -and -not $node) {
    throw "Neither bun nor node was found."
}
$runner = if ($bun) { $bun } else { $node.Source }

function Find-ClaudeMemScript {
    param([string[]]$Names)
    foreach ($name in $Names) {
        foreach ($base in @($plugin, (Join-Path $plugin "scripts"), (Join-Path $plugin "plugin\scripts"))) {
            $candidate = Join-Path $base $name
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    return $null
}

$script = switch ($Mode) {
    "mcp-server" { Find-ClaudeMemScript @("mcp-server.cjs", "mcp-server.js") }
    "worker" { Find-ClaudeMemScript @("worker-service.cjs", "worker-service.js") }
    "version-check" { Find-ClaudeMemScript @("version-check.cjs", "version-check.js") }
    default {
        $wrapper = Find-ClaudeMemScript @("worker-wrapper.cjs", "worker-wrapper.js")
        if ($wrapper) { $wrapper } else { Find-ClaudeMemScript @("worker-service.cjs", "worker-service.js") }
    }
}

if ([string]::IsNullOrWhiteSpace($script) -or -not (Test-Path -LiteralPath $script)) {
    throw "claude-mem entrypoint not found: $script"
}

$env:CLAUDE_MEM_DATA_DIR = if ($env:CLAUDE_MEM_DATA_DIR) { $env:CLAUDE_MEM_DATA_DIR } else { Join-Path $env:USERPROFILE ".claude-mem" }
$env:CLAUDE_MEM_WORKER_HOST = if ($env:CLAUDE_MEM_WORKER_HOST) { $env:CLAUDE_MEM_WORKER_HOST } else { "127.0.0.1" }
$env:CLAUDE_MEM_WORKER_PORT = if ($env:CLAUDE_MEM_WORKER_PORT) { $env:CLAUDE_MEM_WORKER_PORT } else { "37700" }
$env:CLAUDE_MEM_CHROMA_ENABLED = if ($env:CLAUDE_MEM_CHROMA_ENABLED) { $env:CLAUDE_MEM_CHROMA_ENABLED } else { "false" }
$env:CLAUDE_MEM_MANAGED = "true"

$extraArgs = @()
if ($null -ne $Arguments) {
    $extraArgs = @($Arguments | Where-Object { -not [string]::IsNullOrEmpty($_) })
}
& $runner $script @extraArgs
exit $LASTEXITCODE
