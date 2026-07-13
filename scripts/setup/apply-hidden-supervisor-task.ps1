$ErrorActionPreference='Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\wscript.exe" -Argument "`"$root\scripts\setup\start-windows-supervisor-hidden.vbs`" `"$root`"" -WorkingDirectory $root
Set-ScheduledTask -TaskName 'HiveMind-Supervisor' -Action $action | Out-Null
Start-ScheduledTask -TaskName 'HiveMind-Supervisor'