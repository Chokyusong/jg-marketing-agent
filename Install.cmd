@echo off
rem JG Marketing Agent - one-time setup for a new PC.
rem Finds Python 3.12+, makes .venv, installs requirements.txt, then opens the program.
rem The work (and the Korean messages) is in scripts\install.ps1.
rem Options: -NoPause -NoLaunch (for automated tests)
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %*
set "code=%errorlevel%"
endlocal & exit /b %code%
