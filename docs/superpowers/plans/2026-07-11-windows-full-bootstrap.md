# Windows Full Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make native Windows local-full provision missing host prerequisites, preserve existing Hive-Mind memory, and resume safely after a required reboot.

**Architecture:** Keep host provisioning, project-data backup, and project installation separate. A prerequisite script exposes a dry-run/testable API and invokes WinGet only in live mode; a backup script creates a manifest plus a consistent SQLite copy before install.ps1 repairs .venv. install.ps1 remains the orchestrator.

**Tech Stack:** PowerShell 5.1+, WinGet, WSL2, Docker Desktop, Ollama, uv, Bun, Node LTS, Rustup, Visual Studio Build Tools, Python 3.12, pytest/smoke PowerShell scripts.

## Global Constraints

- Preserve cerebro/, hive_mind.db, .env, and existing MCP configuration; only .venv may be recreated.
- Use paths derived from $Root; never hardcode a user profile path.
- Install packages only with explicit WinGet IDs and package/source agreements passed to that invocation.
- A pending restart blocks all later project-install phases.
- Tests use dry-run or mocked command invokers; they never download packages or alter host software.
- local-min remains backward compatible. Host provisioning is automatic only for local-full unless skipped.

---

## File structure

- Create: scripts/setup/bootstrap-prerequisites.ps1 — package detection, WinGet install, reboot/resume state, validation.
- Create: scripts/setup/backup-install-state.ps1 — timestamped vault/config manifest and consistent UMC backup.
- Modify: install.ps1 — switches and preflight ordering.
- Create: tests/install/test_windows_bootstrap.ps1 — dry-run PowerShell contract tests.
- Modify: tests/smoke/test_smoke.ps1, docs/installation.md, README.md.

### Task 1: Implement testable prerequisite provisioning

**Files:**
- Create: scripts/setup/bootstrap-prerequisites.ps1
- Test: tests/install/test_windows_bootstrap.ps1

**Interfaces:**
- Produces Get-HiveMindPrerequisites -Profile <string>, returning objects with Name, WinGetId, Command, Required, Installed, and Reason.
- Produces Invoke-HiveMindPrerequisiteBootstrap -Profile <string> -DryRun <bool> -SkipWsl <bool> -CommandRunner <scriptblock>, returning Ready, RestartRequired, Missing, and Installed.
- Consumes Test-HiveMindCommand from scripts/lib/HiveMind.Windows.psm1.

- [ ] **Step 1: Write the failing test**

    . "$Root\scripts\setup\bootstrap-prerequisites.ps1"
    $result = Invoke-HiveMindPrerequisiteBootstrap -Profile local-full -DryRun -CommandRunner {
        param($file, $arguments)
        [pscustomobject]@{ ExitCode = 0; Output = "" }
    }
    Assert-True (-not $result.RestartRequired) "dry run must not require a restart"
    Assert-True ($null -ne $result.Missing) "result must expose missing prerequisites"

- [ ] **Step 2: Run it to verify failure**

Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1

Expected: fail because the bootstrap script does not exist.

- [ ] **Step 3: Implement minimal bootstrap API**

    function Get-HiveMindPrerequisites {
        param([ValidateSet("local-min","local-full")][string]$Profile)
        $items = @(
            @{ Name="Git"; WinGetId="Git.Git"; Command="git"; Required=$true },
            @{ Name="uv"; WinGetId="Astral.UV"; Command="uv"; Required=$true },
            @{ Name="Bun"; WinGetId="Oven-sh.Bun"; Command="bun"; Required=$true },
            @{ Name="Node LTS"; WinGetId="OpenJS.NodeJS.LTS"; Command="node"; Required=$true },
            @{ Name="Rustup"; WinGetId="Rustlang.Rustup"; Command="cargo"; Required=$true },
            @{ Name="Ollama"; WinGetId="Ollama.Ollama"; Command="ollama"; Required=$true },
            @{ Name="Docker Desktop"; WinGetId="Docker.DockerDesktop"; Command="docker"; Required=($Profile -eq "local-full") }
        )
        foreach ($item in $items) {
            [pscustomobject]@{ Name=$item.Name; WinGetId=$item.WinGetId; Command=$item.Command
              Required=$item.Required; Installed=(Test-HiveMindCommand $item.Command)
              Reason="command $($item.Command) not on PATH" }
        }
    }

    function Invoke-HiveMindPrerequisiteBootstrap {
        param([string]$Profile, [switch]$DryRun, [switch]$SkipWsl, [scriptblock]$CommandRunner)
        # Require winget in live mode. Install each missing required item with exact package args.
        # Validate docker version, ollama list, and wsl status after installation.
        # Persist restart state under backups/install-state and return RestartRequired when needed.
    }

The live package command must be exactly: winget install --id <id> --exact --silent --accept-source-agreements --accept-package-agreements. WSL uses wsl --status and wsl --install when unavailable.

- [ ] **Step 4: Run the test to verify pass**

Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1

Expected: PASS: prerequisite dry-run contract.

- [ ] **Step 5: Commit**

    git add scripts/setup/bootstrap-prerequisites.ps1 tests/install/test_windows_bootstrap.ps1
    git commit -m "feat: bootstrap Windows prerequisites"

### Task 2: Snapshot protected data before runtime repair

**Files:**
- Create: scripts/setup/backup-install-state.ps1
- Modify: tests/install/test_windows_bootstrap.ps1

**Interfaces:**
- Produces New-HiveMindInstallSnapshot -Root <string> -OutputRoot <string>, returning SnapshotPath, ManifestPath, DatabaseBackupPath, and Hashes.
- Reads but never modifies the live vault, UMC, environment, or MCP configuration.

- [ ] **Step 1: Write the failing test**

    $snapshot = New-HiveMindInstallSnapshot -Root $fixtureRoot -OutputRoot $fixtureBackups
    Assert-True (Test-Path $snapshot.ManifestPath) "manifest must be written"
    Assert-True (Test-Path $snapshot.DatabaseBackupPath) "database backup must be written"
    Assert-Equal (Get-FileHash "$fixtureRoot\.env").Hash $snapshot.Hashes[".env"]

- [ ] **Step 2: Run it to verify failure**

Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1

Expected: fail because New-HiveMindInstallSnapshot is undefined.

- [ ] **Step 3: Implement the snapshot**

    function New-HiveMindInstallSnapshot {
        param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$OutputRoot)
        $snapshot = Join-Path $OutputRoot ("install-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
        New-Item -ItemType Directory -Path $snapshot -Force | Out-Null
        # Copy cerebro/, .env, and managed MCP files preserving relative paths.
        # Run SQLite Connection.backup() through Python 3.12 for hive_mind.db.
        # Run PRAGMA integrity_check on copied DB and emit manifest.json with SHA-256 hashes.
    }

- [ ] **Step 4: Run it to verify pass**

Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1

Expected: PASS: snapshot preserves protected data.

- [ ] **Step 5: Commit**

    git add scripts/setup/backup-install-state.ps1 tests/install/test_windows_bootstrap.ps1
    git commit -m "feat: snapshot memory before Windows install"

### Task 3: Wire the safe bootstrap into the native installer

**Files:**
- Modify: install.ps1
- Modify: tests/install/test_windows_bootstrap.ps1

**Interfaces:**
- Consumes New-HiveMindInstallSnapshot and Invoke-HiveMindPrerequisiteBootstrap.
- Adds -SkipPrerequisites and -PrerequisitesOnly.

- [ ] **Step 1: Write the failing orchestration test**

    $text = Get-Content "$Root\install.ps1" -Raw
    Assert-Match $text "\[switch\]\$SkipPrerequisites"
    Assert-Match $text "New-HiveMindInstallSnapshot"
    Assert-Match $text "Invoke-HiveMindPrerequisiteBootstrap"

- [ ] **Step 2: Run it to verify failure**

Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1

Expected: fail because switches/calls are absent.

- [ ] **Step 3: Add parameters and preflight order**

    [switch]$SkipPrerequisites,
    [switch]$PrerequisitesOnly

    . (Join-Path $Root "scripts\setup\backup-install-state.ps1")
    . (Join-Path $Root "scripts\setup\bootstrap-prerequisites.ps1")
    Step "Protected memory snapshot"
    $snapshot = New-HiveMindInstallSnapshot -Root $Root -OutputRoot (Join-Path $Root "backups")
    if (-not $SkipPrerequisites -and $Profile -eq "local-full") {
        Step "Host prerequisites"
        $preflight = Invoke-HiveMindPrerequisiteBootstrap -Profile $Profile
        if ($preflight.RestartRequired) { throw "Restart Windows, then rerun install.ps1 -Profile $Profile." }
    }
    if ($PrerequisitesOnly) { return }

Place this before Ensure-HiveMindPythonRuntime; do not alter the current local-min path.

- [ ] **Step 4: Run it to verify pass**

Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1

Expected: PASS: installer invokes safe bootstrap.

- [ ] **Step 5: Commit**

    git add install.ps1 tests/install/test_windows_bootstrap.ps1
    git commit -m "feat: run Windows full bootstrap safely"

### Task 4: Enforce full-stack validation and document operation

**Files:**
- Modify: install.ps1
- Modify: tests/smoke/test_smoke.ps1
- Modify: docs/installation.md
- Modify: README.md

**Interfaces:**
- local-full invokes scripts/setup/verify_wrappers.py --require-docker after Docker is reachable.

- [ ] **Step 1: Write failing smoke assertions**

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$Root\scripts\setup\bootstrap-prerequisites.ps1" -Profile local-full -DryRun
    if ($LASTEXITCODE -ne 0) { throw "bootstrap dry-run failed" }
    if (-not (Select-String -LiteralPath "$Root\install.ps1" -Pattern "verify_wrappers.py.*--require-docker" -Quiet)) {
        throw "local-full wrapper validation missing"
    }

- [ ] **Step 2: Run it to verify failure**

Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/smoke/test_smoke.ps1

Expected: fail until strict validation is added.

- [ ] **Step 3: Implement strict validation and docs**

    if ($Profile -eq "local-full") {
        Invoke-HiveMindPython -Root $Root -Arguments @("scripts/setup/verify_wrappers.py", "--require-docker")
    } else {
        Invoke-HiveMindPython -Root $Root -Arguments @("scripts/setup/verify_wrappers.py")
    }

Document -SkipPrerequisites, -PrerequisitesOnly, restart/resume semantics, and snapshots under backups/install-<timestamp>/.

- [ ] **Step 4: Run the smoke and dry-run tests**

Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1; powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/smoke/test_smoke.ps1

Expected: success without downloads or host software changes.

- [ ] **Step 5: Commit**

    git add install.ps1 tests/smoke/test_smoke.ps1 docs/installation.md README.md
    git commit -m "docs: document full Windows bootstrap"

### Task 5: Reinstall full and verify memory retention

**Files:**
- Runtime-only changes: .venv/, backups/install-*/, Docker volumes, local model cache, and agent MCP configuration.

**Interfaces:**
- Consumes final install.ps1 contract.
- Produces a health report and matching pre/post protected-data manifest.

- [ ] **Step 1: Record pre-install hashes**

    Get-FileHash hive_mind.db, .env
    Get-ChildItem cerebro -Recurse -File | Get-FileHash

- [ ] **Step 2: Execute the installer**

Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Profile local-full -WithTests

Expected: verified snapshot, healthy prerequisites, Docker services, repaired .venv, and tests.

- [ ] **Step 3: Resume if restart is required**

Run after restarting Windows: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Profile local-full -WithTests

Expected: installed prerequisites are not downloaded again and the project phase continues.

- [ ] **Step 4: Verify memory and services**

    & .\.venv\Scripts\python.exe scripts\utils\recovery.py verify
    & .\.venv\Scripts\python.exe scripts\services\sinapse-write.py health
    docker compose -f docker-compose.falkordb.yml ps
    docker compose -f integrations\milvus\docker-compose.yml ps
    docker compose -f integrations\ragflow\docker-compose.yml ps

Expected: SQLite integrity is ok, memory health returns data, and local-full containers are running.

- [ ] **Step 5: Commit code and documentation if the worktree is clean**

    git status --short
    git add install.ps1 scripts/setup tests docs README.md
    git commit -m "feat: complete Windows full installer"

## Plan self-review

- Spec coverage: Task 1 covers provisioning/idempotence/reboot state; Task 2 protects memory; Task 3 fixes orchestration order; Task 4 validates and documents it; Task 5 performs full reinstall and retention validation.
- Placeholder scan: no TODO/TBD markers or unspecified test steps.
- Interface consistency: Tasks 2 and 3 use the exact names defined by Tasks 1 and 2.
