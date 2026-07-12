Set-StrictMode -Version Latest

$libraryPath = Join-Path (Split-Path -Parent $PSScriptRoot) "lib\HiveMind.Windows.psm1"
Import-Module $libraryPath -Force

function Test-HiveMindVisualStudioBuildTools {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path -LiteralPath $vswhere)) { return $false }
    $installationPath = & $vswhere -products * -requires Microsoft.Component.MSBuild -property installationPath 2>$null | Select-Object -First 1
    return -not [string]::IsNullOrWhiteSpace([string]$installationPath)
}

function Get-HiveMindVisualStudioMsBuildDirectory {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path -LiteralPath $vswhere)) { return $null }
    $installationPath = & $vswhere -products * -requires Microsoft.Component.MSBuild -property installationPath 2>$null | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace([string]$installationPath)) { return $null }
    $directory = Join-Path $installationPath "MSBuild\Current\Bin"
    if (Test-Path -LiteralPath $directory) { return $directory }
    return $null
}
function Update-HiveMindPrerequisitePath {
    $visualStudioMsBuild = Get-HiveMindVisualStudioMsBuildDirectory
    $locations = @(
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"),
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".bun\bin"),
        (Join-Path $env:USERPROFILE ".cargo\bin"),
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin"),
        $visualStudioMsBuild
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    $wingetPackages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path -LiteralPath $wingetPackages) {
        $locations += Get-ChildItem -LiteralPath $wingetPackages -Recurse -File -Include "uv.exe", "bun.exe" -ErrorAction SilentlyContinue |
            ForEach-Object { Split-Path -Parent $_.FullName }
    }
    $visualStudioMsBuild = Get-HiveMindVisualStudioMsBuildDirectory
    $locations = @($locations | Select-Object -Unique)
    foreach ($location in $locations) {
        if (($env:PATH -split ';') -notcontains $location) { $env:PATH = "$location;$env:PATH" }
    }
}
function Get-HiveMindPrerequisites {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("local-min", "local-full")]
        [string]$Profile
    )

    $fullProfile = $Profile -eq "local-full"
    $items = @(
        @{ Name = "Git"; WinGetId = "Git.Git"; Command = "git"; Required = $true },
        @{ Name = "uv"; WinGetId = "astral-sh.uv"; Command = "uv"; Required = $true },
        @{ Name = "Bun"; WinGetId = "Oven-sh.Bun"; Command = "bun"; Required = $true },
        @{ Name = "Node LTS"; WinGetId = "OpenJS.NodeJS.LTS"; Command = "node"; Required = $true },
        @{ Name = "Rustup"; WinGetId = "Rustlang.Rustup"; Command = "cargo"; Required = $true },
        @{ Name = "Ollama"; WinGetId = "Ollama.Ollama"; Command = "ollama"; Required = $true },
        @{ Name = "Docker Desktop"; WinGetId = "Docker.DockerDesktop"; Command = "docker"; Required = $fullProfile },
        @{ Name = "WSL 2"; WinGetId = $null; Command = "wsl"; Required = $fullProfile },
        @{ Name = "Visual Studio Build Tools"; WinGetId = "Microsoft.VisualStudio.2022.BuildTools"; Command = "msbuild"; Required = $fullProfile }
    )

    foreach ($item in $items) {
        $installed = if ($item.Name -eq "Visual Studio Build Tools") { Test-HiveMindVisualStudioBuildTools } else { Test-HiveMindCommand $item.Command }
        [pscustomobject]@{
            Name = $item.Name
            WinGetId = $item.WinGetId
            Command = $item.Command
            Required = $item.Required
            Installed = $installed
            Reason = if ($installed) { "command $($item.Command) is on PATH" } else { "command $($item.Command) not on PATH" }
        }
    }
}

function Invoke-HiveMindPrerequisiteBootstrap {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("local-min", "local-full")]
        [string]$Profile,

        [switch]$DryRun,
        [switch]$SkipWsl,
        [scriptblock]$CommandRunner
    )

    if ($null -eq $CommandRunner) {
        $CommandRunner = {
            param($file, $arguments)
            $output = & $file @arguments 2>&1
            [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = ($output -join "`n") }
        }
    }

    Update-HiveMindPrerequisitePath
    $prerequisites = @(Get-HiveMindPrerequisites -Profile $Profile)
    $required = @($prerequisites | Where-Object Required)
    if ($SkipWsl) {
        $required = @($required | Where-Object Name -ne "WSL 2")
    }

    $missing = @($required | Where-Object { -not $_.Installed })
    if ($DryRun) {
        return [pscustomobject]@{
            Ready = $missing.Count -eq 0
            RestartRequired = $false
            Missing = @($missing)
            Installed = @($required | Where-Object Installed)
        }
    }

    if ($missing.Count -gt 0 -and -not (Test-HiveMindCommand "winget")) {
        throw "winget is required to install Hive-Mind prerequisites. Install App Installer and run this command again."
    }

    $restartRequired = $false
    foreach ($item in $missing) {
        if ($item.Name -eq "WSL 2") {
            $result = & $CommandRunner "wsl" @("--install")
        } else {
            $result = & $CommandRunner "winget" @("install", "--id", $item.WinGetId, "--exact", "--silent", "--accept-source-agreements", "--accept-package-agreements")
        }

        if ($result.ExitCode -in @(3010, 1641)) {
            $restartRequired = $true
            $root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
            $stateDirectory = Join-Path $root "backups\install-state"
            New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
            [pscustomobject]@{
                Profile = $Profile
                RestartRequired = $true
                UpdatedAt = (Get-Date).ToString("o")
            } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stateDirectory "prerequisites.json") -Encoding UTF8
            return [pscustomobject]@{
                Ready = $false
                RestartRequired = $true
                Missing = @($missing)
                Installed = @($required | Where-Object Installed)
            }
        }
        if ($result.ExitCode -ne 0) {
            throw "Failed to install $($item.Name): $($result.Output)"
        }
    }

    if (-not $SkipWsl -and $Profile -eq "local-full") {
        $wslStatus = & $CommandRunner "wsl" @("--status")
        if ($wslStatus.ExitCode -ne 0) {
            throw "WSL 2 validation failed: $($wslStatus.Output)"
        }
    }

    foreach ($validation in @(
        @{ Name = "Docker Desktop"; Command = "docker"; Arguments = @("version") },
        @{ Name = "Ollama"; Command = "ollama"; Arguments = @("list") }
    )) {
        if ($validation.Name -eq "Docker Desktop" -and $Profile -ne "local-full") { continue }
        $result = & $CommandRunner $validation.Command $validation.Arguments
        if ($result.ExitCode -ne 0) {
            throw "$($validation.Name) validation failed: $($result.Output)"
        }
    }


    $final = @(Get-HiveMindPrerequisites -Profile $Profile)
    $finalRequired = @($final | Where-Object Required)
    if ($SkipWsl) {
        $finalRequired = @($finalRequired | Where-Object Name -ne "WSL 2")
    }
    $finalMissing = @($finalRequired | Where-Object { -not $_.Installed })
    return [pscustomobject]@{
        Ready = $finalMissing.Count -eq 0 -and -not $restartRequired
        RestartRequired = $restartRequired
        Missing = @($finalMissing)
        Installed = @($finalRequired | Where-Object Installed)
    }
}
