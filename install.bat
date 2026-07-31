@echo off
setlocal

set "ROOT=%~dp0"
set "DRIVER=%ROOT%scripts\setup\windows_install_entry.py"
if exist "%ROOT%.venv\Scripts\python.exe" (
  "%ROOT%.venv\Scripts\python.exe" "%DRIVER%" --root "%ROOT:~0,-1%" %*
) else (
  py.exe -3 "%DRIVER%" --root "%ROOT:~0,-1%" %*
)
exit /b %ERRORLEVEL%
