# =============================================================================
# Vault write enforcement — Windows native (BETA)
# =============================================================================
# Same model as the Linux/macOS script: a dedicated local service account
# (hive-dreamer) owns cerebro\; the human keeps Modify for editing (Obsidian);
# everyone else is denied; agents deposit only into cerebro\90-intake\.
#
# BETA: validated on paper against icacls semantics, not yet on hardware.
# Review the output; -Status and -Revert are provided.
#
# Usage (PowerShell as Administrator, from the project root):
#   .\scripts\setup\setup-vault-enforcement.ps1            # apply
#   .\scripts\setup\setup-vault-enforcement.ps1 -Status    # inspect only
#   .\scripts\setup\setup-vault-enforcement.ps1 -Revert    # undo
# =============================================================================
[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Revert
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$VaultDir    = Join-Path $ProjectRoot 'cerebro'
$IntakeDir   = Join-Path $VaultDir '90-intake'
$ServiceUser = if ($env:HIVE_SERVICE_USER) { $env:HIVE_SERVICE_USER } else { 'hive-dreamer' }
$HumanUser   = $env:USERNAME

function Show-Status {
    Write-Host "Vault:        $VaultDir"
    if (Test-Path $VaultDir) {
        $acl = Get-Acl $VaultDir
        Write-Host "Owner:        $($acl.Owner)"
        Write-Host "Intake:       $IntakeDir ($(if (Test-Path $IntakeDir) { 'present' } else { 'missing' }))"
    }
    $svc = Get-LocalUser -Name $ServiceUser -ErrorAction SilentlyContinue
    Write-Host "Service user: $(if ($svc) { $svc.Name } else { 'not created' })"
    $probe = Join-Path $VaultDir '.write-probe'
    try {
        New-Item -Path $probe -ItemType File -Force | Out-Null
        Remove-Item $probe -Force
        Write-Host 'Enforcement:  OFF (current user can write directly to the vault)'
    } catch {
        Write-Host 'Enforcement:  ON (direct vault write denied for current user)'
    }
}

if ($Status) { Show-Status; exit 0 }

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error 'This script must run in an elevated (Administrator) PowerShell.'
    exit 1
}
if (-not (Test-Path $VaultDir)) {
    Write-Error "Vault not found at $VaultDir"
    exit 1
}

if ($Revert) {
    Write-Host "Reverting: returning vault control to $HumanUser..."
    icacls $VaultDir /reset /T /C | Out-Null
    icacls $VaultDir /setowner $HumanUser /T /C | Out-Null
    Write-Host '  OK enforcement reverted (service account kept; remove manually if desired).'
    exit 0
}

Write-Host 'Applying vault write enforcement (Windows native, BETA)...'

# 1. Dedicated local service account (no interactive logon needed; random
#    password, never used — services run via supervisor with RunAs if desired).
if (-not (Get-LocalUser -Name $ServiceUser -ErrorAction SilentlyContinue)) {
    Add-Type -AssemblyName 'System.Web'
    $pw = [System.Web.Security.Membership]::GeneratePassword(24, 4)
    $sec = ConvertTo-SecureString $pw -AsPlainText -Force
    New-LocalUser -Name $ServiceUser -Password $sec -PasswordNeverExpires `
        -UserMayNotChangePassword -Description 'Hive-Mind vault service account' | Out-Null
}
Write-Host "  OK service account $ServiceUser"

# 2. Vault ACLs: break inheritance; service user full control; human Modify
#    (Obsidian/Syncthing); nothing for Users/Everyone.
icacls $VaultDir /inheritance:r /T /C | Out-Null
icacls $VaultDir /setowner $ServiceUser /T /C | Out-Null
icacls $VaultDir /grant "${ServiceUser}:(OI)(CI)F" /T /C | Out-Null
icacls $VaultDir /grant "${HumanUser}:(OI)(CI)M" /T /C | Out-Null
icacls $VaultDir /grant 'SYSTEM:(OI)(CI)F' /T /C | Out-Null
Write-Host "  OK vault owned by $ServiceUser; $HumanUser keeps Modify; others denied"

# 3. Intake: the single surface writable by any authenticated local account
#    (agents running under other users still get to deposit suggestions).
if (-not (Test-Path $IntakeDir)) { New-Item -Path $IntakeDir -ItemType Directory | Out-Null }
icacls $IntakeDir /grant '*S-1-5-11:(OI)(CI)M' /C | Out-Null   # Authenticated Users
Write-Host "  OK intake writable by authenticated users: $IntakeDir"

Write-Host ''
Show-Status
Write-Host ''
Write-Host 'Note: agents running under your own account inherit your Modify grant.'
Write-Host 'For full adversarial enforcement, run agents under a separate local user.'
