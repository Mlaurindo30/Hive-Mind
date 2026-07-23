[CmdletBinding()]
param(
  [string]$Root=(Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
  [switch]$WhatIfOnly,
  [string]$BackupDir
)
$ErrorActionPreference='Stop'
$python=Join-Path $Root '.venv\Scripts\python.exe'
$hiveMind=Join-Path $Root '.venv\Scripts\hive-mind.exe'

# D008-R1V retired the standalone maintenance wrapper: the audit + retention
# logic now lives behind `hive-mind backup run --apply`, which config/runtime.yaml
# schedules as the `backup-databases` job. That wrapper only ever existed as an
# untracked file on the maintainer's machine, so a cutover that replaces the
# working tree would leave HiveMind-Backup pointing at a target that no longer
# exists. Migrating the task is therefore part of installing, not a manual step.
$jobs=@(
 @{Name='HiveMind-DreamCycle'; Script='scripts\dream\dream_cycle.py'; Daily=$true},
 @{Name='HiveMind-ClaudeMemBridge'; Script='scripts\services\claude_mem_bridge.py'; Daily=$true},
 @{Name='HiveMind-KnowledgeHealth'; Script='scripts\health\audit_memory.py'; Daily=$true},
 @{Name='HiveMind-Backup'; Execute=$hiveMind; Arguments='backup run --apply'; Daily=$true}
)

function Export-HiveMindTaskDefinition {
  <#
    .SYNOPSIS
      Save a task's current XML so a migration can be rolled back.
    .OUTPUTS
      The backup file path, or $null when the task does not exist yet.
  #>
  param([Parameter(Mandatory)][string]$TaskName,[Parameter(Mandatory)][string]$Destination)
  $existing=Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if(-not $existing){return $null}
  if(-not(Test-Path -LiteralPath $Destination)){New-Item -ItemType Directory -Path $Destination -Force|Out-Null}
  $stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
  $file=Join-Path $Destination "$TaskName.$stamp.xml"
  Export-ScheduledTask -TaskName $TaskName|Set-Content -LiteralPath $file -Encoding UTF8
  return $file
}

function Restore-HiveMindTaskDefinition {
  <#
    .SYNOPSIS
      Roll a task back to a definition captured by Export-HiveMindTaskDefinition.
  #>
  param([Parameter(Mandatory)][string]$TaskName,[Parameter(Mandatory)][string]$Path)
  if(-not(Test-Path -LiteralPath $Path)){throw "rollback definition not found: $Path"}
  $xml=Get-Content -LiteralPath $Path -Raw
  Register-ScheduledTask -TaskName $TaskName -Xml $xml -Force|Out-Null
}

if(-not $BackupDir){$BackupDir=Join-Path $Root 'logs\scheduled-tasks'}

foreach($job in $jobs){
 if($WhatIfOnly){Write-Host $job.Name;continue}

 if($job.Execute){
   # Native command job. The executable must exist before the task is written,
   # otherwise the migration would trade a broken target for another one.
   if(-not(Test-Path -LiteralPath $job.Execute)){
     Write-Warning "$($job.Name): $($job.Execute) not found; leaving the existing task untouched."
     continue
   }
   $backup=Export-HiveMindTaskDefinition -TaskName $job.Name -Destination $BackupDir
   if($backup){Write-Host "$($job.Name): previous definition saved to $backup"}
   $action=New-ScheduledTaskAction -Execute $job.Execute -Argument $job.Arguments -WorkingDirectory $Root
 }
 else{
   $target=Join-Path $Root $job.Script
   if(-not(Test-Path $target)){continue}
   $action=New-ScheduledTaskAction -Execute $python -Argument ('"'+$target+'"') -WorkingDirectory $Root
 }

 $trigger=New-ScheduledTaskTrigger -Daily -At '02:00'
 Register-ScheduledTask -TaskName $job.Name -Action $action -Trigger $trigger -Description 'Hive-Mind scheduled knowledge job' -Force|Out-Null
}
