Set-StrictMode -Version Latest

function Test-HiveMindIsWindows {
    return $env:OS -eq "Windows_NT"
}

function Get-HiveMindRoot {
    param(
        [string]$StartPath = $PSScriptRoot
    )

    $current = Resolve-Path -LiteralPath $StartPath
    while ($null -ne $current) {
        $path = $current.Path
        if ((Test-Path -LiteralPath (Join-Path $path "pyproject.toml")) -and
            (Test-Path -LiteralPath (Join-Path $path "install.sh"))) {
            return $path
        }
        $parent = Split-Path -LiteralPath $path -Parent
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $path) {
            break
        }
        $current = Get-Item -LiteralPath $parent
    }

    throw "Could not find Hive-Mind repository root from $StartPath"
}

function Get-HiveMindVenvScripts {
    param(
        [string]$Root = (Get-HiveMindRoot)
    )

    if (Test-HiveMindIsWindows) {
        return Join-Path $Root ".venv\Scripts"
    }
    return Join-Path $Root ".venv/bin"
}

function Get-HiveMindPython {
    param(
        [string]$Root = (Get-HiveMindRoot),
        [switch]$AllowSystem
    )

    $venvPython = if (Test-HiveMindIsWindows) {
        Join-Path $Root ".venv\Scripts\python.exe"
    } else {
        Join-Path $Root ".venv/bin/python"
    }

    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }

    if (-not $AllowSystem) {
        throw "Project Python was not found at $venvPython. Run install.bat first."
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return $py.Source
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    throw "Python was not found. Install Python 3.10+ or create .venv."
}

function Test-HiveMindPythonVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    if ($Version -notmatch '(?m)^\s*Python\s+(\d+)\.(\d+)') {
        return $false
    }

    return [int]$Matches[1] -eq 3 -and [int]$Matches[2] -eq 12
}

function Test-HiveMindPythonRuntime {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )
    $payload = Invoke-HiveMindNativeWindowsSupport -Root $Root -Arguments @("test-python-runtime", "--root", $Root)
    if ([string]::IsNullOrWhiteSpace($payload)) { return $false }
    $decoded = $payload | ConvertFrom-Json
    return [bool]$decoded.Ready
}

function Repair-HiveMindPythonRuntime {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )
    Invoke-HiveMindNativeWindowsSupport -Root $Root -Arguments @("repair-python-runtime", "--root", $Root) | Out-Null
}

function Ensure-HiveMindPythonRuntime {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )
    Invoke-HiveMindNativeWindowsSupport -Root $Root -Arguments @("ensure-python-runtime", "--root", $Root) | Out-Null
}

function Invoke-HiveMindPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [string]$Root = (Get-HiveMindRoot),
        [switch]$AllowSystem
    )

    $python = Get-HiveMindPython -Root $Root -AllowSystem:$AllowSystem
    Push-Location -LiteralPath $Root
    $oldPythonUtf8 = [Environment]::GetEnvironmentVariable("PYTHONUTF8", "Process")
    $oldPythonIoEncoding = [Environment]::GetEnvironmentVariable("PYTHONIOENCODING", "Process")
    try {
        [Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "Process")
        [Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "Process")
        if ((Split-Path -Leaf $python) -ieq "py.exe") {
            & $python -3.12 @Arguments
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            return
        }

        & $python @Arguments
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        [Environment]::SetEnvironmentVariable("PYTHONUTF8", $oldPythonUtf8, "Process")
        [Environment]::SetEnvironmentVariable("PYTHONIOENCODING", $oldPythonIoEncoding, "Process")
        Pop-Location
    }
}

function Invoke-HiveMindNativeWindowsSupport {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [string]$Root = (Get-HiveMindRoot)
    )

    $moduleRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $python = Get-HiveMindPython -Root $moduleRoot -AllowSystem
    Push-Location -LiteralPath $moduleRoot
    try {
        $output = & $python -m hive_mind.install.windows_support @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        return ($output -join "`n")
    } finally {
        Pop-Location
    }
}

function Invoke-HiveMindCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$Arguments = @(),

        [string]$Root = (Get-HiveMindRoot),
        [hashtable]$ExtraEnvironment = @{}
    )

    Push-Location -LiteralPath $Root
    $oldValues = @{}
    try {
        foreach ($key in $ExtraEnvironment.Keys) {
            $oldValues[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
            [Environment]::SetEnvironmentVariable($key, [string]$ExtraEnvironment[$key], "Process")
        }

        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        foreach ($key in $ExtraEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($key, $oldValues[$key], "Process")
        }
        Pop-Location
    }
}

function Read-HiveMindDotEnv {
    param(
        [string]$Root = (Get-HiveMindRoot)
    )

    $envPath = Join-Path $Root ".env"
    $values = @{}
    if (-not (Test-Path -LiteralPath $envPath)) {
        return $values
    }

    foreach ($line in Get-Content -LiteralPath $envPath) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) { continue }
        $parts = $trimmed -split "=", 2
        if ($parts.Count -eq 2) {
            $values[$parts[0].Trim()] = $parts[1].Trim().Trim('"').Trim("'")
        }
    }
    return $values
}


function Apply-HiveMindProfileContract {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileContract,

        [string]$Root = (Get-HiveMindRoot),

        [switch]$DryRun
    )

    $args = @("apply-profile-contract", "--root", $Root, "--profile-contract", $ProfileContract)
    if ($DryRun) { $args += "--dry-run" }
    $payload = Invoke-HiveMindNativeWindowsSupport -Root $Root -Arguments $args
    if ([string]::IsNullOrWhiteSpace($payload)) { return @() }
    $decoded = $payload | ConvertFrom-Json
    return @($decoded)
}
function Set-HiveMindDotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Value,

        [string]$Root = (Get-HiveMindRoot)
    )

    Invoke-HiveMindNativeWindowsSupport -Root $Root -Arguments @(
        "set-dotenv-value",
        "--root", $Root,
        "--name", $Name,
        "--value", $Value
    ) | Out-Null
}

function Import-HiveMindDotEnv {
    param(
        [string]$Root = (Get-HiveMindRoot)
    )

    $payload = Invoke-HiveMindNativeWindowsSupport -Root $Root -Arguments @("read-dotenv", "--root", $Root)
    $values = if ([string]::IsNullOrWhiteSpace($payload)) { @{} } else { $payload | ConvertFrom-Json -AsHashtable }
    foreach ($key in $values.Keys) {
        [Environment]::SetEnvironmentVariable($key, [string]$values[$key], "Process")
    }
    return $values
}

function New-HiveMindApiKey {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd("=") -replace "\+", "-" -replace "/", "_"
}

function Sync-HiveMindVaultTemplates {
    <#
    .SYNOPSIS
    Materializes shipped vault templates without replacing user-owned files.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    Invoke-HiveMindNativeWindowsSupport -Root $Root -Arguments @("sync-vault-templates", "--root", $Root) | Out-Null
}
function Ensure-HiveMindDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Test-HiveMindCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Remove-HiveMindOldFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [int]$Days,

        [string]$Filter = "*"
    )

    if (-not (Test-Path -LiteralPath $Path)) { return }
    $cutoff = (Get-Date).AddDays(-1 * $Days)
    Get-ChildItem -LiteralPath $Path -Filter $Filter -File |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        Remove-Item -Force
}

Export-ModuleMember -Function *
