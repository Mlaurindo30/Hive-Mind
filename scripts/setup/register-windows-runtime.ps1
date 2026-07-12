[CmdletBinding()]
param([string]$Root = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)), [switch]$WhatIfOnly)
$ErrorActionPreference = 'Stop'
$supervisor = Join-Path $Root 'scripts\setup\start-windows-supervisor.ps1'
$validator = Join-Path $Root 'scripts\health\validate_after_reboot_windows.py'
$python = Join-Path $Root '.venv\Scripts\python.exe'
$tasks = @(
  @{ Name='HiveMind-Supervisor'; Execute='powershell.exe'; Arguments='-NoProfile -ExecutionPolicy Bypass -File "' + $supervisor + '" -Root "' + $Root + '"'; Trigger=(New-ScheduledTaskTrigger -AtLogOn) },
  @{ Name='HiveMind-PostRebootValidation'; Execute=$python; Arguments='"' + $validator + '"'; Trigger=(New-ScheduledTaskTrigger -AtLogOn) }
)
foreach($task in $tasks) {
  if($WhatIfOnly) { Write-Host $task.Name; continue }
  $action=New-ScheduledTaskAction -Execute $task.Execute -Argument $task.Arguments -WorkingDirectory $Root
  Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger $task.Trigger -Description 'Hive-Mind native Windows runtime' -Force | Out-Null
}