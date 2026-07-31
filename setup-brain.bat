@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Hive-Mind Python was not found at "%PYTHON%".
  echo Run install.bat first.
  exit /b 1
)
"%PYTHON%" "%ROOT%scripts\setup\setup-brain.py" %*
exit /b %ERRORLEVEL%
