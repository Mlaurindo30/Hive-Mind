[CmdletBinding()]
param(
    [ValidateSet("local-min", "local-full")]
    [string]$Profile = "local-min",

    [switch]$Force,
    [switch]$WithTests,
    [switch]$WithRealTests,
    [switch]$SkipAgents,
    [switch]$SkipServices,
    [switch]$NonInteractive,
    [switch]$SkipPrerequisites,
    [switch]$PrerequisitesOnly,
    [switch]$InstallPrerequisites,
    [switch]$DryRun,
    [switch]$Repair,
    [switch]$Update,
    [switch]$Uninstall,
    [switch]$PreserveVault,
    [switch]$PreserveDatabase,
    [switch]$SystemService
)

$ErrorActionPreference = "Stop"

if ($Repair -and $Uninstall) {
    throw "Repair and Uninstall cannot be combined."
}
if ($Update -and $Uninstall) {
    throw "Update and Uninstall cannot be combined."
}
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Import-Module (Join-Path $Root "scripts\lib\HiveMind.Windows.psm1") -Force -DisableNameChecking

Set-Location -LiteralPath $Root
. (Join-Path $Root "scripts\setup\backup-install-state.ps1")
. (Join-Path $Root "scripts\setup\bootstrap-prerequisites.ps1")

$profileContract = Join-Path $Root "config\profiles\$Profile.env.example"
if (-not (Test-Path -LiteralPath $profileContract)) {
    throw "Profile contract was not found: $profileContract"
}

if ($DryRun) {
    Write-Host "Profile contract: $profileContract"`r`n    Write-Host "==> Dry-run: validating prerequisite contract only"
    $preflight = Invoke-HiveMindPrerequisiteBootstrap -Profile $Profile -DryRun
    $missingNames = @($preflight.Missing | ForEach-Object { $_.Name })
    Write-Host "Dry-run complete. Ready=$($preflight.Ready); Missing=$($missingNames -join ', ')"
    return
}

Write-Host "`n==> Protected memory snapshot"
$snapshot = New-HiveMindInstallSnapshot -Root $Root -OutputRoot (Join-Path $Root "backups")
Write-Host "Verified snapshot: $($snapshot.SnapshotPath)"

if (($Profile -eq "local-full" -or $InstallPrerequisites) -and -not $SkipPrerequisites) {
    Write-Host "`n==> Host prerequisites"
    $preflight = Invoke-HiveMindPrerequisiteBootstrap -Profile $Profile
    if ($preflight.RestartRequired) {
        Write-Host "Windows restart required. Rerun: .\install.ps1 -Profile $Profile"
        exit 3010
    }
    if (-not $preflight.Ready) {
        throw "Required host prerequisites remain unavailable: $($preflight.Missing.Name -join ', ')"
    }
}
if ($PrerequisitesOnly) { return }

function Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message"
}

function Require-Command {
    param([string]$Name, [string]$Hint)
    if (-not (Test-HiveMindCommand $Name)) {
        throw "$Name was not found. $Hint"
    }
}

function Import-VsBuildEnvironment {
    if (Get-Command cl.exe -ErrorAction SilentlyContinue) {
        return
    }

    $candidates = @(@(
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
        "$env:ProgramFiles\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) })

    if (-not $candidates) {
        Write-Warning "MSVC compiler environment not found. hnswlib may fail to build."
        return
    }

    $vsDevCmd = $candidates[0]
    Write-Host "Loading MSVC build environment from $vsDevCmd"
    $lines = cmd.exe /s /c "`"$vsDevCmd`" -arch=x64 -host_arch=x64 >nul && set"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to load Visual Studio Build Tools environment from $vsDevCmd"
    }

    foreach ($line in $lines) {
        $parts = $line -split "=", 2
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
        }
    }

    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
        throw "Visual Studio Build Tools was found, but cl.exe is still unavailable after loading VsDevCmd.bat"
    }
}

function Find-BunPath {
    $cmd = Get-Command bun -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $candidate = Get-ChildItem -LiteralPath $wingetRoot -Recurse -Filter "bun.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if ($candidate) { return $candidate }
    return $null
}

function Find-CargoPath {
    $cmd = Get-Command cargo -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidate = Join-Path $env:USERPROFILE ".cargo\bin\cargo.exe"
    if (Test-Path -LiteralPath $candidate) { return $candidate }
    return $null
}

function Find-OllamaPath {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:LOCALAPPDATA "Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    return $null
}

function Add-OllamaModel {
    param(
        [System.Collections.Generic.HashSet[string]]$Models,
        [string]$Model
    )
    if ([string]::IsNullOrWhiteSpace($Model)) { return }
    $trimmed = $Model.Trim()
    if ($trimmed.EndsWith(":cloud")) { return }
    [void]$Models.Add($trimmed)
}

function Get-HiveMindEnvValue {
    param(
        [hashtable]$Values,
        [string]$Name,
        [string]$Default = ""
    )
    if ($Values.ContainsKey($Name) -and -not [string]::IsNullOrWhiteSpace([string]$Values[$Name])) {
        return [string]$Values[$Name]
    }
    return $Default
}

function Install-OllamaModels {
    $ollama = Find-OllamaPath
    if (-not $ollama) {
        Write-Warning "Ollama was not found; skipping local model download. Install Ollama and run install.ps1 again."
        return
    }

    $envValues = Read-HiveMindDotEnv -Root $Root
    $models = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

    Add-OllamaModel -Models $models -Model (Get-HiveMindEnvValue -Values $envValues -Name "OLLAMA_EMBED_MODEL" -Default "snowflake-arctic-embed2:latest")
    Add-OllamaModel -Models $models -Model (Get-HiveMindEnvValue -Values $envValues -Name "HIVE_GRAPHITI_MODEL" -Default "qwen2.5:3b")
    Add-OllamaModel -Models $models -Model (Get-HiveMindEnvValue -Values $envValues -Name "HIVE_LIGHTRAG_MODEL" -Default "qwen2.5:3b")

    foreach ($role in @("DREAMER", "GRAPHIFY", "VISION", "OCR", "SYNTHESIS", "CLAUDE_MEM")) {
        foreach ($suffix in @("", "FALLBACK_", "FALLBACK2_")) {
            $providerKey = "HIVE_${role}_${suffix}PROVIDER"
            $modelKey = "HIVE_${role}_${suffix}MODEL"
            $provider = if ($envValues.ContainsKey($providerKey)) { [string]$envValues[$providerKey] } else { "" }
            $model = if ($envValues.ContainsKey($modelKey)) { [string]$envValues[$modelKey] } else { "" }
            if ($provider -ieq "ollama") {
                Add-OllamaModel -Models $models -Model $model
            }
        }
    }

    if ($models.Count -eq 0) {
        Write-Host "No local Ollama models configured."
        return
    }

    Write-Host "Ensuring Ollama models: $([string]::Join(', ', $models))"
    foreach ($model in $models) {
        & $ollama pull $model
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}

function Test-ClaudeMemRuntime {
    $cacheRoot = Join-Path $env:USERPROFILE ".claude\plugins\cache\thedotmack\claude-mem"
    $knownRoots = @(
        (Join-Path $env:USERPROFILE ".claude\plugins\marketplaces\thedotmack\plugin\scripts"),
        (Join-Path $env:USERPROFILE ".codex\plugins\cache\thedotmack\claude-mem\scripts"),
        (Join-Path $cacheRoot "13.6.2\scripts"),
        (Join-Path $cacheRoot "13.6.1\scripts"),
        (Join-Path $cacheRoot "13.6.0\scripts")
    )
    foreach ($known in $knownRoots) {
        if ((Test-Path -LiteralPath (Join-Path $known "worker-service.cjs")) -and
            (Test-Path -LiteralPath (Join-Path $known "mcp-server.cjs"))) {
            return $true
        }
    }
    try {
        $worker = Get-ChildItem -LiteralPath $cacheRoot -Recurse -Filter "worker-service.cjs" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        $mcp = Get-ChildItem -LiteralPath $cacheRoot -Recurse -Filter "mcp-server.cjs" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        return ($null -ne $worker -and $null -ne $mcp)
    } catch {
        return $false
    }
}

function Install-ClaudeMemCodex {
    if (-not (Test-HiveMindCommand npx)) {
        Write-Warning "npx not found; skipping claude-mem native installer."
        return
    }
    $bun = Find-BunPath
    if (-not $bun) {
        Write-Warning "bun not found; skipping claude-mem worker runtime install."
        return
    }

    $oldPath = $env:PATH
    try {
        if (Test-HiveMindCommand node) {
            $cli = Join-Path $Root "npm\bin\hive-mind.js"
            if (Test-Path -LiteralPath $cli) {
                & node $cli "services" "stop" | Out-Host
            }
        }

        $env:PATH = (Split-Path -Parent $bun) + ";" + $env:PATH
        $env:CLAUDE_MEM_DATA_DIR = Join-Path $env:USERPROFILE ".claude-mem"
        $env:FASTEMBED_CACHE_PATH = Join-Path $env:CLAUDE_MEM_DATA_DIR "models"
        Ensure-HiveMindDirectory -Path $env:CLAUDE_MEM_DATA_DIR
        Ensure-HiveMindDirectory -Path $env:FASTEMBED_CACHE_PATH
        $stdout = Join-Path $env:TEMP "hive-mind-claude-mem-install.out.log"
        $stderr = Join-Path $env:TEMP "hive-mind-claude-mem-install.err.log"
        $proc = Start-Process -FilePath "cmd.exe" -ArgumentList @(
            "/c", "echo.|npx -y claude-mem@13.6 install --ide codex-cli --runtime worker --provider claude --no-auto-start"
        ) -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        $installCode = $proc.ExitCode
        if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout | Out-Host }
        if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr | Out-Host }
        if ($installCode -ne 0) {
            if (Test-ClaudeMemRuntime) {
                Write-Warning "claude-mem installer returned $installCode, but the worker and MCP runtime files are installed. Continuing."
            } else {
                exit $installCode
            }
        }
    } finally {
        $env:PATH = $oldPath
    }
}

function Build-Rtk {
    $rtk = Join-Path $Root "integrations\rtk\target\release\rtk.exe"
    if (Test-Path -LiteralPath $rtk) {
        & $rtk --version | Out-Host
        return
    }

    $cargo = Find-CargoPath
    if (-not $cargo) {
        Write-Warning "cargo not found; install Rustup to compile RTK."
        return
    }

    Import-VsBuildEnvironment
    Push-Location -LiteralPath (Join-Path $Root "integrations\rtk")
    try {
        & $cargo build --locked --release
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}

function Invoke-LocalFullCompose {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ComposeFile,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $ComposeFile)) {
        throw "$Name compose file was not found at $ComposeFile"
    }

    Write-Host "Starting $Name from $ComposeFile"
    & docker compose -f $ComposeFile up -d --quiet-pull
    if ($LASTEXITCODE -ne 0) {
        throw "$Name docker compose startup failed."
    }
}

function Start-LocalFullStack {
    Require-Command docker "Install Docker Desktop and keep it running for local-full."

    & docker version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker is installed, but the Docker engine is not reachable. Start Docker Desktop and rerun install.ps1 -Profile local-full."
    }

    Invoke-LocalFullCompose -Name "FalkorDB" -ComposeFile (Join-Path $Root "docker-compose.falkordb.yml")
    Invoke-LocalFullCompose -Name "Milvus" -ComposeFile (Join-Path $Root "integrations\milvus\docker-compose.yml")
    Invoke-LocalFullCompose -Name "RAGFlow" -ComposeFile (Join-Path $Root "integrations\ragflow\docker-compose.yml")

    Set-HiveMindDotEnvValue -Root $Root -Name "VECTOR_BACKEND" -Value "milvus"
    Set-HiveMindDotEnvValue -Root $Root -Name "MILVUS_URI" -Value "http://localhost:19530"
    Set-HiveMindDotEnvValue -Root $Root -Name "HIVE_KNOWLEDGE_HEALTH_MILVUS" -Value "1"
    Set-HiveMindDotEnvValue -Root $Root -Name "FALKORDB_HOST" -Value "localhost"
    Set-HiveMindDotEnvValue -Root $Root -Name "FALKORDB_PORT" -Value "6379"
    Set-HiveMindDotEnvValue -Root $Root -Name "RAGFLOW_BASE" -Value "http://localhost:9380"
}

Step "Preflight"
Require-Command uv "Install uv: winget install Astral.UV"
if (-not (Test-HiveMindCommand git)) {
    Write-Warning "git was not found. scripts/setup/components.py bootstrap will need it for integrations."
}
if (-not (Test-HiveMindCommand node)) {
    Write-Warning "node was not found. The service supervisor and claude-mem install will be skipped."
}
Import-VsBuildEnvironment

Step "Project virtual environment"
# Repair-HiveMindPythonRuntime provisions with `uv python install 3.12` and
# recreates the environment with `uv venv --python 3.12 --clear .venv`.
if ($Force -and (Test-Path -LiteralPath (Join-Path $Root ".venv"))) {
    throw "-Force does not delete .venv automatically. Remove it yourself if you want a clean rebuild."
}
Ensure-HiveMindPythonRuntime -Root $Root

Step "Environment file"
$envPath = Join-Path $Root ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    $example = Join-Path $Root ".env.example"
    if (Test-Path -LiteralPath $example) {
        Copy-Item -LiteralPath $example -Destination $envPath
    } else {
        New-Item -ItemType File -Path $envPath | Out-Null
    }
}
$appliedProfileValues = @(Apply-HiveMindProfileContract -Root $Root -ProfileContract $profileContract)
Write-Host "Applied profile defaults: $($appliedProfileValues -join ', ')"
$envValues = Read-HiveMindDotEnv -Root $Root
if (-not $envValues.ContainsKey("HIVE_MIND_API_KEY") -or [string]::IsNullOrWhiteSpace($envValues["HIVE_MIND_API_KEY"])) {
    Set-HiveMindDotEnvValue -Root $Root -Name "HIVE_MIND_API_KEY" -Value (New-HiveMindApiKey)
}
if ($Profile -eq "local-full") {
    Step "Local-full container stack"
    Start-LocalFullStack
} else {
    Set-HiveMindDotEnvValue -Root $Root -Name "VECTOR_BACKEND" -Value "sqlite_vec"
}
Import-HiveMindDotEnv -Root $Root | Out-Null

Step "Ollama local models"
Install-OllamaModels

Step "Pinned integrations"
Require-Command git "Install Git before bootstrapping pinned integrations."
foreach ($component in @("graphify", "neural-memory", "rtk")) {
    $componentPath = Join-Path $Root "integrations\$component"
    if (Test-Path -LiteralPath (Join-Path $componentPath ".git")) {
        $resolvedComponentPath = (Resolve-Path -LiteralPath $componentPath).Path.Replace("\\", "/")
        & git config --global --add safe.directory $resolvedComponentPath
        if ($LASTEXITCODE -ne 0) { throw "Could not mark $componentPath as a trusted Git checkout." }
    }
}
Invoke-HiveMindPython -Root $Root -AllowSystem -Arguments @("scripts/setup/components.py", "bootstrap")

Step "Python dependencies with uv"
& uv sync --frozen --all-groups
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Invoke-HiveMindPython -Root $Root -Arguments @("-c", "import pydantic, watchdog")

Step "Wrapper and UMC setup"
if ($Profile -eq "local-full") {
    Invoke-HiveMindPython -Root $Root -Arguments @("scripts/setup/verify_wrappers.py", "--require-docker")
} else {
    Invoke-HiveMindPython -Root $Root -Arguments @("scripts/setup/verify_wrappers.py")
}
Invoke-HiveMindPython -Root $Root -Arguments @("scripts/setup/setup_umc.py")

Step "Vault materialization"
$vault = Join-Path $Root "cerebro"
$templateVault = Join-Path $Root "templates\vault"
if (-not (Test-Path -LiteralPath $vault) -and (Test-Path -LiteralPath $templateVault)) {
    Copy-Item -LiteralPath $templateVault -Destination $vault -Recurse
}
$vaultDirs = @(
    "cortex\temporal\_global",
    "cortex\temporal\hipocampo",
    "cortex\temporal\arquivo",
    "cortex\frontal\decisoes",
    "cortex\frontal\trabalho\active",
    "cortex\frontal\trabalho\ativo",
    "cortex\frontal\trabalho\arquivo",
    "cortex\frontal\projetos",
    "cortex\frontal\brain",
    "cortex\frontal\org\people",
    "cortex\frontal\org\teams",
    "cortex\parietal\inbox\visual",
    "cortex\parietal\inbox\documents",
    "cortex\parietal\referencias",
    "cortex\parietal\analises",
    "cortex\occipital\capturas-visuais",
    "cortex\occipital\grafo",
    "cortex\insula\saude",
    "cortex\insula\conflitos",
    "cerebelo\sessoes",
    "cerebelo\diario",
    "cerebelo\semanal",
    "cerebelo\padroes",
    "diencefalo\setores",
    "diencefalo\roteamento",
    "tronco\modelos",
    "tronco\paineis",
    "tronco\infra",
    "tronco\meta",
    "90-intake"
)
foreach ($dir in $vaultDirs) {
    Ensure-HiveMindDirectory -Path (Join-Path $vault $dir)
}

Step "Graph/index bootstrap"
$buildGraph = Join-Path $Root "scripts\graph\build-graph.ps1"
if (Test-Path -LiteralPath $buildGraph) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildGraph
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Warning "build-graph.ps1 not found yet; skipping graph build."
}

if (-not $SkipAgents) {
    Step "MCP registration"
    $register = Join-Path $Root "scripts\setup\register-mcp.ps1"
    if (Test-Path -LiteralPath $register) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $register
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } else {
        Write-Warning "register-mcp.ps1 not found yet; skipping MCP registration."
    }
}

if (-not $SkipServices -and (Test-HiveMindCommand node)) {
    Step "claude-mem native runtime"
    Install-ClaudeMemCodex

    Step "RTK"
    Build-Rtk

    Step "Services"
    Invoke-HiveMindPython -Root $Root -Arguments @("scripts/setup/install_services.py", "manifest")
    $oldHome = $env:HIVE_MIND_HOME
    try {
        $env:HIVE_MIND_HOME = $Root
        & node (Join-Path $Root "npm\bin\hive-mind.js") "services" "restart"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & node (Join-Path $Root "npm\bin\hive-mind.js") "services" "status"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        $env:HIVE_MIND_HOME = $oldHome
    }
}

if (-not $SkipServices) {
    Step "Windows autostart"
    $registerRuntime = Join-Path $Root "scripts\setup\register-windows-runtime.ps1"
    if (Test-Path -LiteralPath $registerRuntime) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $registerRuntime -Root $Root
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}
if ($WithTests) {
    Step "Tests"
    $runAll = Join-Path $Root "tests\run_all.ps1"
    if (Test-Path -LiteralPath $runAll) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runAll
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}

if ($WithRealTests) {
    Step "Real knowledge tests"
    $real = Join-Path $Root "tests\run_real_knowledge.ps1"
    if (Test-Path -LiteralPath $real) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $real
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}

Step "Done"
Write-Host "Hive-Mind Windows install finished in $Root"
