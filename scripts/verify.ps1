# Verify the repository: ruff check, then pytest -q.
# Exits non-zero if any step fails. Works on Windows PowerShell 5.1.
# Usage: .\scripts\verify.ps1 [extra pytest args]
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) {
    Write-Host '[verify] FAILED: .venv not found.'
    Write-Host '  py -3.12 -m venv .venv'
    Write-Host '  .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt'
    exit 2
}

Push-Location $root
try {
    Write-Host '[verify] 1/2 ruff check .'
    & $py -m ruff check .
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host "[verify] FAILED: ruff check (exit $code)"
        exit $code
    }

    Write-Host '[verify] 2/2 pytest -q'
    & $py -m pytest -q @args
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host "[verify] FAILED: pytest (exit $code)"
        exit $code
    }

    Write-Host '[verify] OK: ruff and pytest passed'
    exit 0
}
finally {
    Pop-Location
}
