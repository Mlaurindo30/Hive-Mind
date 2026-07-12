[CmdletBinding()]
param(
    [switch]$WhatIfOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$audit = Join-Path $Root "scripts\maintenance\backup-audit-daily.ps1"
$prune = Join-Path $Root "scripts\maintenance\backup-prune-weekly.ps1"

$tasks = @(
    @{ Name = "Hive-Mind Backup Audit Daily"; Script = $audit; At = "03:10"; Weekly = $false },
    @{ Name = "Hive-Mind Backup Prune Weekly"; Script = $prune; At = "03:30"; Weekly = $true }
)

foreach ($task in $tasks) {
    Write-Host "$($task.Name) -> $($task.Script)"
    if ($WhatIfOnly) { continue }
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$($task.Script)`""
    $trigger = if ($task.Weekly) {
        New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At $task.At
    } else {
        New-ScheduledTaskTrigger -Daily -At $task.At
    }
    Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger $trigger -Description "Hive-Mind maintenance" -Force | Out-Null
}
