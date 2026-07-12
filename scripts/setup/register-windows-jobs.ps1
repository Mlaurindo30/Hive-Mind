[CmdletBinding()]
param([string]$Root=(Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),[switch]$WhatIfOnly)
$ErrorActionPreference='Stop'
$python=Join-Path $Root '.venv\Scripts\python.exe'
$jobs=@(
 @{Name='HiveMind-DreamCycle'; Script='scripts\dream\dream_cycle.py'; Daily=$true},
 @{Name='HiveMind-ClaudeMemBridge'; Script='scripts\services\claude_mem_bridge.py'; Daily=$true},
 @{Name='HiveMind-KnowledgeHealth'; Script='scripts\health\audit_memory.py'; Daily=$true},
 @{Name='HiveMind-Backup'; Script='scripts\maintenance\backup.py'; Daily=$true}
)
foreach($job in $jobs){
 if($WhatIfOnly){Write-Host $job.Name;continue}
 $target=Join-Path $Root $job.Script
 if(-not(Test-Path $target)){continue}
 $action=New-ScheduledTaskAction -Execute $python -Argument ('"'+$target+'"') -WorkingDirectory $Root
 $trigger=New-ScheduledTaskTrigger -Daily -At '02:00'
 Register-ScheduledTask -TaskName $job.Name -Action $action -Trigger $trigger -Description 'Hive-Mind scheduled knowledge job' -Force|Out-Null
}