@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-brain.ps1" %*
exit /b %ERRORLEVEL%
