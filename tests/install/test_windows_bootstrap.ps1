$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw "Assertion failed: $Message"
    }
}

function Assert-Contains {
    param(
        [object[]]$Values,
        [string]$Expected,
        [string]$Message
    )

    if ($Values -notcontains $Expected) {
        throw "Assertion failed: $Message. Expected '$Expected' in '$($Values -join ', ')'"
    }
}

. "$Root\scripts\setup\bootstrap-prerequisites.ps1"
. "$Root\scripts\setup\fullstack-readiness.ps1"

$fullStack = Test-HiveMindFullStackReadiness -Root $Root -Profile local-full -Probe {
    param([string]$Name)
    return $false
}
Assert-True (-not $fullStack.Ready) "local-full must reject unavailable required services"
Assert-Contains -Values $fullStack.Missing -Expected "docker-desktop" -Message "Docker must be reported when unavailable"

$result = Invoke-HiveMindPrerequisiteBootstrap -Profile local-full -DryRun -CommandRunner {
    param($file, $arguments)
    [pscustomobject]@{ ExitCode = 0; Output = "" }
}

Assert-True (-not $result.RestartRequired) "dry run must not require a restart"
Assert-True ($null -ne $result.Missing) "result must expose missing prerequisites"

$fullPrerequisites = @(Get-HiveMindPrerequisites -Profile local-full)
$wsl = @($fullPrerequisites | Where-Object Name -eq "WSL 2")
$buildTools = @($fullPrerequisites | Where-Object Name -eq "Visual Studio Build Tools")
Assert-True ($wsl.Count -eq 1 -and $wsl[0].Required) "local-full must require WSL 2"
Assert-True ($buildTools.Count -eq 1 -and $buildTools[0].Required) "local-full must require Visual Studio Build Tools"

$originalCommandTest = ${function:Test-HiveMindCommand}
$statePath = Join-Path $Root "backups\install-state\prerequisites.json"
$calls = [System.Collections.Generic.List[object]]::new()
try {
    function global:Test-HiveMindCommand {
        param([string]$Name)
        return $Name -eq "winget"
    }
    $restart = Invoke-HiveMindPrerequisiteBootstrap -Profile local-full -CommandRunner {
        param($file, $arguments)
        $calls.Add([pscustomobject]@{ File = $file; Arguments = @($arguments) })
        [pscustomobject]@{ ExitCode = 3010; Output = "restart required" }
    }
    Assert-True $restart.RestartRequired "restart result must request a reboot"
    Assert-True ($calls.Count -eq 1) "no installs or validations may run after restart is required"
    Assert-True ($calls[0].File -eq "winget") "first missing prerequisite must use winget"
    Assert-True (($calls[0].Arguments -join "|") -eq "install|--id|Git.Git|--exact|--silent|--accept-source-agreements|--accept-package-agreements") "winget arguments must be exact"
    Assert-True (Test-Path -LiteralPath $statePath) "restart state must be persisted before return"
} finally {
    Set-Item -Path function:global:Test-HiveMindCommand -Value $originalCommandTest
    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
}

. "$Root\scripts\setup\backup-install-state.ps1"
$fixtureRoot = Join-Path $env:TEMP ("hive-mind-snapshot-" + [guid]::NewGuid())
$fixtureBackups = Join-Path $fixtureRoot "backups"
try {
    New-Item -ItemType Directory -Path (Join-Path $fixtureRoot "cerebro\cortex") -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $fixtureRoot ".env") -Value "TEST_KEY=value" -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $fixtureRoot "cerebro\cortex\note.md") -Value "preserve me" -Encoding UTF8
    $fixtureDb = Join-Path $fixtureRoot "hive_mind.db"
    $python = (Get-Command python -ErrorAction Stop).Source
    & $python -c "import sqlite3,sys; conn=sqlite3.connect(sys.argv[1]); conn.execute('create table fixture (id integer primary key)'); conn.commit(); conn.close()" $fixtureDb
    if ($LASTEXITCODE -ne 0) { throw "Could not create the isolated SQLite fixture database" }
    $snapshot = New-HiveMindInstallSnapshot -Root $fixtureRoot -OutputRoot $fixtureBackups
    Assert-True (Test-Path -LiteralPath $snapshot.ManifestPath) "snapshot manifest must exist"
    Assert-True (Test-Path -LiteralPath $snapshot.DatabaseBackupPath) "snapshot database must exist"
    Assert-True ((Get-FileHash -LiteralPath (Join-Path $fixtureRoot ".env") -Algorithm SHA256).Hash -eq $snapshot.Hashes[".env"]) "environment hash must match"
    Assert-True (Test-Path -LiteralPath (Join-Path $snapshot.SnapshotPath "cerebro\cortex\note.md")) "vault file must be copied"
} finally {
    if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
}

Write-Host "PASS: prerequisite dry-run contract"
