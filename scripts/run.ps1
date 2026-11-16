# Start the local dashboard at http://127.0.0.1:8765
# Usage: .\scripts\run.ps1 [extra uvicorn args]
# Do not use --reload from stage 8 on: a reload restarts the server and cuts the
# browser job thread (Chrome is left open, the post stays reserved).
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) {
    Write-Host '[run] .venv not found. Run: py -3.12 -m venv .venv'
    Write-Host '      then: .\.venv\Scripts\python.exe -m pip install -r requirements.txt'
    exit 2
}

Push-Location $root
try {
    & $py -m uvicorn app.main:app --host 127.0.0.1 --port 8765 @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
