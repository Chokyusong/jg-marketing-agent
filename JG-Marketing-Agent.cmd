@echo off
rem JG Marketing Agent - double-click to open the dashboard in its own window.
rem The window runs without a console (pythonw). Close the window to quit.
rem Developer browser mode: scripts\run.ps1 (http://127.0.0.1:8765)
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo [JG Marketing Agent] .venv not found in this folder.
    echo.
    echo Run these once in this folder, then double-click this file again:
    echo     py -3.12 -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 2
)

start "" ".venv\Scripts\pythonw.exe" -m app.desktop
endlocal
exit /b 0
