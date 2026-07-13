Option Explicit
Dim shell, root, ps, command
If WScript.Arguments.Count <> 1 Then WScript.Quit 2
root = WScript.Arguments(0)
ps = "powershell.exe"
command = Chr(34) & ps & Chr(34) & " -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & root & "\scripts\setup\start-windows-supervisor.ps1" & Chr(34) & " -Root " & Chr(34) & root & Chr(34)
Set shell = CreateObject("WScript.Shell")
shell.Run command, 0, False