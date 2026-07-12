Set-StrictMode -Version Latest

function Get-HiveMindSha256 {
    param([Parameter(Mandatory)][string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "")
    } finally {
        $sha.Dispose()
        $stream.Dispose()
    }
}
function Get-HiveMindSnapshotSources {
    param([Parameter(Mandatory)][string]$Root)
    $sources = @()
    foreach ($relative in @('cerebro', 'hive_mind.db', '.env', '.mcp.json', 'config\mcp')) {
        $path = Join-Path $Root $relative
        if (Test-Path -LiteralPath $path) {
            $sources += [pscustomobject]@{ RelativePath = $relative; Path = $path }
        }
    }
    return $sources
}

function New-HiveMindInstallSnapshot {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$OutputRoot
    )

    $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    $snapshotPath = Join-Path $OutputRoot ('install-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Path $snapshotPath -Force | Out-Null
    $hashes = @{}
    $databaseBackupPath = $null

    foreach ($source in Get-HiveMindSnapshotSources -Root $resolvedRoot) {
        $destination = Join-Path $snapshotPath $source.RelativePath
        if ((Get-Item -LiteralPath $source.Path).PSIsContainer) {
            Copy-Item -LiteralPath $source.Path -Destination $destination -Recurse -Force
            Get-ChildItem -LiteralPath $source.Path -Recurse -File | ForEach-Object {
                $relative = $_.FullName.Substring($resolvedRoot.Length).TrimStart('\\')
                $hashes[$relative] = Get-HiveMindSha256 -Path $_.FullName
            }
        } elseif ($source.RelativePath -eq 'hive_mind.db') {
            $databaseBackupPath = $destination
            $databaseDirectory = Split-Path -Parent $destination
            New-Item -ItemType Directory -Path $databaseDirectory -Force | Out-Null
            $python = (Get-Command python -ErrorAction Stop).Source
            & $python -c "import sqlite3,sys; source=sqlite3.connect(sys.argv[1]); target=sqlite3.connect(sys.argv[2]); source.backup(target); target.close(); source.close()" $source.Path $destination
            if ($LASTEXITCODE -ne 0) { throw 'SQLite backup failed' }
            $integrity = & $python -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('pragma integrity_check').fetchone()[0])" $destination
            if ($LASTEXITCODE -ne 0 -or ($integrity -join '').Trim() -ne 'ok') { throw 'SQLite backup integrity check failed' }
            $hashes[$source.RelativePath] = Get-HiveMindSha256 -Path $source.Path
        } else {
            $directory = Split-Path -Parent $destination
            New-Item -ItemType Directory -Path $directory -Force | Out-Null
            Copy-Item -LiteralPath $source.Path -Destination $destination -Force
            $hashes[$source.RelativePath] = Get-HiveMindSha256 -Path $source.Path
        }
    }

    $manifestPath = Join-Path $snapshotPath 'manifest.json'
    [pscustomobject]@{
        CreatedAt = (Get-Date).ToUniversalTime().ToString('o')
        SourceRoot = $resolvedRoot
        DatabaseBackupPath = $databaseBackupPath
        Hashes = $hashes
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

    return [pscustomobject]@{
        SnapshotPath = $snapshotPath
        ManifestPath = $manifestPath
        DatabaseBackupPath = $databaseBackupPath
        Hashes = $hashes
    }
}