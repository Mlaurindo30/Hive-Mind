# =============================================================================
# register-mcp.ps1 - thin wrapper (D009-R6)
#
# This script used to be 456 lines of product logic: provider detection, config
# paths, JSON and TOML merging, instruction injection, backups. All of that now
# lives in the Python package, in src/hive_mind/agents/**, where a single
# implementation serves Windows and POSIX alike.
#
# What remains is the only thing a shell script may own: find the executable,
# forward the arguments, preserve the streams, return the exit code.
#
# Every option the old script accepted is still accepted - by the CLI, not by
# this file. See src/hive_mind/agents/compat.py for why the translation lives
# there: a wrapper that reinterpreted its own arguments would be product logic
# again, in the place this delivery removed it from.
# =============================================================================
$ErrorActionPreference = "Stop"

$command = Get-Command hive-mind -ErrorAction SilentlyContinue
if ($null -ne $command) {
    & $command.Source agents register @args
    exit $LASTEXITCODE
}

# The bootstrap creates a virtual environment at the project root. That is the
# documented contract both installers rely on; nothing below is provider-aware.
# PROJECT_ROOT overrides it, exactly as the POSIX wrapper does - the two must
# not diverge on where they look.
$root = $env:PROJECT_ROOT
if ([string]::IsNullOrEmpty($root)) {
    $root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}
foreach ($relative in @("Scripts\hive-mind.exe", "bin/hive-mind")) {
    $candidate = Join-Path $root ".venv\$relative"
    if (Test-Path -LiteralPath $candidate) {
        & $candidate agents register @args
        exit $LASTEXITCODE
    }
}

# Last resort: the package's own module entry point. Used only when the console
# script was not installed, and supported by the package itself.
foreach ($relative in @("Scripts\python.exe", "bin/python")) {
    $candidate = Join-Path $root ".venv\$relative"
    if (Test-Path -LiteralPath $candidate) {
        & $candidate -m hive_mind.cli agents register @args
        exit $LASTEXITCODE
    }
}

Write-Error @"
hive-mind executable not found.

Looked for 'hive-mind' on PATH and under $root\.venv.
Install the package first, for example:

    uv sync
    uv run hive-mind agents register --apply
"@
exit 127
