@echo off
setlocal

call "%~dp0scripts\setup\setup-brain.bat" %*
exit /b %ERRORLEVEL%
