@echo off
rem JG Marketing Agent - double-click to open the dashboard in its own window.
rem The window runs without a console (pythonw). Close the window to quit.
rem Developer browser mode: scripts\run.ps1 (http://127.0.0.1:8765)
rem First run (no .venv yet): scripts\install.ps1 makes .venv and runs
rem pip install -r requirements.txt (2-3 minutes, internet needed), then opens the program.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" -FirstRun %*
    goto :after_install
)

start "" ".venv\Scripts\pythonw.exe" -m app.desktop
endlocal
exit /b 0

:after_install
set "code=%errorlevel%"
endlocal & exit /b %code%
