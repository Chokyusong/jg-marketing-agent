# JG Marketing Agent - one-time setup for a new PC (Windows PowerShell 5.1+).
# Called by Install.cmd and, on the first run, by JG-Marketing-Agent.cmd.
#
#   1. find Python 3.12+   (py -3.12 -> py -3.13 -> python on PATH). Never installs Python.
#   2. make .venv           (skipped when it already works)
#   3. pip install -r requirements.txt   (the only thing downloaded)
#   4. warn (do not stop) when Google Chrome is missing
#   5. launch the program window (unless -NoLaunch)
#
# This file stays ASCII (AGENTS.md). Korean messages are read as UTF-8 from
# scripts\install_messages.txt so they show correctly on the cp949 console.
#
# Switches for automated tests:
#   -NoPause    never wait for a key
#   -NoLaunch   do not open the program window
#   -FirstRun   show the "first run" notice and wait for a key before installing
#   -PyLauncher / -PythonCommand   names to look up (tests pass names that do not exist)
# Exit codes: 0 ready, 1 install failed, 2 Python 3.12+ not found.
param(
    [switch]$NoPause,
    [switch]$NoLaunch,
    [switch]$FirstRun,
    [string]$PyLauncher = 'py',
    [string]$PythonCommand = 'python'
)

$ErrorActionPreference = 'Continue'
$started = Get-Date
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root '.venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
$venvPyw = Join-Path $venv 'Scripts\pythonw.exe'
$requirements = Join-Path $root 'requirements.txt'

# ------------------------------------------------------------------ messages
$messages = @{}
$messageFile = Join-Path $PSScriptRoot 'install_messages.txt'
foreach ($line in [System.IO.File]::ReadAllLines($messageFile, [System.Text.Encoding]::UTF8)) {
    if ($line.StartsWith('#') -or -not $line.Contains('=')) { continue }
    $at = $line.IndexOf('=')
    $messages[$line.Substring(0, $at).Trim()] = $line.Substring($at + 1)
}

function Say([string]$key, [object[]]$values = @(), [string]$color = '') {
    $text = $messages[$key]
    if ($null -eq $text) { $text = $key }
    if ($values.Count -gt 0) { $text = $text -f $values }
    if ($color) { Write-Host $text -ForegroundColor $color } else { Write-Host $text }
}

function Wait-Key([string]$key) {
    if ($NoPause) { return }
    Say $key
    try { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') } catch { Read-Host | Out-Null }
}

function Finish([int]$code) {
    $seconds = [int]((Get-Date) - $started).TotalSeconds
    Say 'elapsed' @($seconds)
    if ($code -ne 0) { Wait-Key 'press_key_end' }
    exit $code
}

# ------------------------------------------------------------------ python
function Get-PythonInfo([string]$exe, [string[]]$prefix) {
    # Returns @{ Version = '3.12'; Path = 'C:\...\python.exe' } or $null.
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { return $null }
    # No double quotes inside: Windows PowerShell 5.1 does not escape them for native programs.
    $probe = 'import sys; print(''%d.%d'' % sys.version_info[:2]); print(sys.executable)'
    try {
        $out = & $exe @prefix -c $probe 2>$null
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0 -or $null -eq $out -or @($out).Count -lt 2) { return $null }
    $lines = @($out)
    return @{ Version = $lines[0].Trim(); Path = $lines[1].Trim() }
}

function Test-NewEnough([string]$version) {
    $parts = $version.Split('.')
    if ($parts.Count -lt 2) { return $false }
    return ([int]$parts[0] -gt 3) -or (([int]$parts[0] -eq 3) -and ([int]$parts[1] -ge 12))
}

function Find-Python {
    foreach ($tag in @('-3.12', '-3.13')) {
        $info = Get-PythonInfo $PyLauncher @($tag)
        if ($info -and (Test-NewEnough $info.Version)) { return $info }
    }
    $info = Get-PythonInfo $PythonCommand @()
    if ($info) {
        if (Test-NewEnough $info.Version) { return $info }
        Say 'python_too_old' @($info.Version) 'Yellow'
    }
    return $null
}

# ------------------------------------------------------------------ checks
$modules = @('fastapi', 'uvicorn', 'jinja2', 'httpx', 'dotenv', 'yaml', 'webview', 'playwright',
             'youtube_transcript_api')

function Test-VenvReady {
    if (-not (Test-Path -LiteralPath $venvPy) -or -not (Test-Path -LiteralPath $venvPyw)) { return $false }
    $names = ($modules | ForEach-Object { "'$_'" }) -join ','
    $code = "import importlib.util, sys; missing = [m for m in [$names] if importlib.util.find_spec(m) is None]; sys.exit(1 if missing else 0)"
    & $venvPy -c $code 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Test-Chrome {
    $paths = @(
        (Join-Path ${env:ProgramFiles} 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:LOCALAPPDATA} 'Google\Chrome\Application\chrome.exe')
    )
    foreach ($p in $paths) { if ($p -and (Test-Path -LiteralPath $p)) { return $true } }
    foreach ($hive in @('HKLM:', 'HKCU:')) {
        $key = "$hive\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
        if (Test-Path $key) { return $true }
    }
    return $false
}

function Start-Program {
    if ($NoLaunch) { return }
    Say 'launching'
    Start-Process -FilePath $venvPyw -ArgumentList @('-m', 'app.desktop') -WorkingDirectory $root
}

# ------------------------------------------------------------------ main
try { $Host.UI.RawUI.WindowTitle = $messages['title'] } catch { }
Write-Host ''
Say 'title' @() 'Cyan'
Write-Host ''

if (Test-VenvReady) {
    Say 'already_ready' @() 'Green'
    if (-not (Test-Chrome)) { Say 'chrome_missing' @() 'Yellow' }
    Start-Program
    Finish 0
}

if ($FirstRun) {
    Say 'first_run'
    Say 'only_requirements'
    Wait-Key 'press_key'
}

if (-not (Test-Chrome)) { Say 'chrome_missing' @() 'Yellow' }

if (Test-Path -LiteralPath $venvPy) {
    Say 'venv_exists'
} else {
    Say 'looking_python'
    $python = Find-Python
    if (-not $python) {
        Say 'python_missing' @() 'Red'
        Say 'python_get_page'
        Say 'python_get_winget'
        Say 'python_then'
        Finish 2
    }
    Say 'python_found' @($python.Version, $python.Path)
    Say 'venv_making'
    & $python.Path -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPy)) {
        Say 'venv_failed' @() 'Red'
        Finish 1
    }
}

Say 'pip_installing'
& $venvPy -m pip install --disable-pip-version-check -r $requirements
if ($LASTEXITCODE -ne 0) {
    Say 'pip_failed' @() 'Red'
    Finish 1
}
if (-not (Test-VenvReady)) {
    Say 'check_failed' @() 'Red'
    Finish 1
}

Write-Host ''
Say 'done' @() 'Green'
Start-Program
Finish 0
