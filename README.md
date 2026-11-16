# JG Marketing AI Agent — Stage 1

This is the first executable project skeleton for the JG Group AI PM track-2 assignment. It intentionally contains **no automated posting to YouTube**. The UI is a non-interactive initial dashboard.

## Prerequisite
- Windows 11
- Python 3.10 or later (Python launcher `py` preferred)

## Run (PowerShell)
```powershell
cd "D:\Projects\JG-Marketing-Agent"
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8765
```
Open http://127.0.0.1:8765 in your browser.

## Run tests (new terminal)
```powershell
cd "D:\Projects\JG-Marketing-Agent"
.\.venv\Scripts\python.exe -m pytest -q
```

## Stage 1 acceptance checklist
- [ ] Local dashboard opens
- [ ] Three columns display: import / AI analysis / review
- [ ] `http://127.0.0.1:8765/api/health` returns `status: ok`
- [ ] Tests pass

## Stage 2 roadmap
YouTube Data API (authorized public metadata and comments) + URL parser + robust error handling.

## Safety / data protection
Do not commit `.env`, keys, tokens, session cookies or browser profiles to public source control.
Use a transparent, human-reviewed marketing workflow. No impersonation or automated deceptive comments.
