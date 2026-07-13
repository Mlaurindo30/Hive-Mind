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
        throw "Project Python was not found at $venvPython. Run install.ps1 first."
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

    $python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        return $false
    }

    try {
        $version = & $python --version 2>&1
    } catch {
        return $false
    }

    if ($LASTEXITCODE -ne 0) {
        return $false
    }

    return Test-HiveMindPythonVersion -Version ($version -join "`n")
}

function Repair-HiveMindPythonRuntime {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    & uv python install 3.12
    if ($LASTEXITCODE -ne 0) {
        throw "uv could not provision Python 3.12"
    }

    & uv venv --python 3.12 --clear (Join-Path $Root ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "uv could not create the project virtual environment"
    }
}

function Ensure-HiveMindPythonRuntime {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    if (-not (Test-HiveMindPythonRuntime -Root $Root)) {
        Repair-HiveMindPythonRuntime -Root $Root
    }
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

    if (-not (Test-Path -LiteralPath $ProfileContract)) {
        throw "Profile contract was not found: $ProfileContract"
    }

    $applied = @()
    foreach ($line in Get-Content -LiteralPath $ProfileContract) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) { continue }

        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) { continue }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ([string]::IsNullOrWhiteSpace($name)) { continue }

        # A profile contract must only contain non-secret defaults. Keep this
        # guard so a future template mistake cannot replace an operator secret.
        if ($name -match '(?i)(api[_-]?key|token|secret|password|credential)') {
            continue
        }

        $applied += $name
        if (-not $DryRun) {
            Set-HiveMindDotEnvValue -Root $Root -Name $name -Value $value
        }
    }

    return $applied
}
function Set-HiveMindDotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Value,

        [string]$Root = (Get-HiveMindRoot)
    )

    $envPath = Join-Path $Root ".env"
    $lines = @()
    if (Test-Path -LiteralPath $envPath) {
        $lines = @(Get-Content -LiteralPath $envPath)
    }

    $pattern = "^\s*$([regex]::Escape($Name))\s*="
    $updated = $false
    $next = foreach ($line in $lines) {
        if ($line -match $pattern) {
            $updated = $true
            "$Name=$Value"
        } else {
            $line
        }
    }

    if (-not $updated) {
        $next += "$Name=$Value"
    }

    Set-Content -LiteralPath $envPath -Value $next -Encoding UTF8
}

function Import-HiveMindDotEnv {
    param(
        [string]$Root = (Get-HiveMindRoot)
    )

    $values = Read-HiveMindDotEnv -Root $Root
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

    $templateVault = Join-Path $Root "templates\vault"
    if (-not (Test-Path -LiteralPath $templateVault -PathType Container)) {
        throw "Shipped vault template directory was not found: $templateVault"
    }

    $vault = Join-Path $Root "cerebro"
    Ensure-HiveMindDirectory -Path $vault
    foreach ($source in Get-ChildItem -LiteralPath $templateVault -Recurse -Force) {
        $relative = $source.FullName.Substring($templateVault.Length + 1)
        $destination = Join-Path $vault $relative
        if ($source.PSIsContainer) {
            Ensure-HiveMindDirectory -Path $destination
            continue
        }

        if (-not (Test-Path -LiteralPath $destination)) {
            Ensure-HiveMindDirectory -Path (Split-Path -Path $destination -Parent)
            Copy-Item -LiteralPath $source.FullName -Destination $destination
        }
    }
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
