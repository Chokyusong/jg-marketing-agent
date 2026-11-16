# Open normal Chrome (no automation) with a JG Marketing Agent profile folder,
# so a person can sign in to Google / YouTube once. Stage 8 (DESIGN 6.3).
#
# Usage (PowerShell, repo root):
#   .\scripts\setup_profile.ps1            # profile-1 (shown as YouTube1 in the app)
#   .\scripts\setup_profile.ps1 -Profile 2
#   .\scripts\setup_profile.ps1 -Profile 1 -WindowPosition "-1860,60"
#
# - Profile folders live OUTSIDE the repository:
#     %LOCALAPPDATA%\JGMarketingAgent\profiles\profile-<N>
#   (override with the JG_PROFILES_DIR environment variable, same as the app).
# - This script only starts chrome.exe with --user-data-dir. It does not type,
#   click or post anything. Sign in by hand, then close the Chrome window.
# - Close this Chrome window before running a job with the same profile
#   (Chrome does not allow two instances on one profile folder).
# - Never commit or share the profile folder: it holds your Google session.
param(
    [ValidateRange(1, 99)]
    [int]$Profile = 1,
    [string]$WindowPosition = '',
    [string]$ChromePath = ''
)
$ErrorActionPreference = 'Stop'

function Find-Chrome {
    param([string]$Configured)
    if ($Configured) {
        if (Test-Path -LiteralPath $Configured -PathType Leaf) { return $Configured }
        return $null
    }
    $bases = @($env:LOCALAPPDATA, $env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:ProgramW6432)
    foreach ($base in $bases) {
        if (-not $base) { continue }
        $candidate = Join-Path $base 'Google\Chrome\Application\chrome.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    $keys = @(
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe'
    )
    foreach ($key in $keys) {
        try {
            $value = (Get-ItemProperty -LiteralPath $key -ErrorAction Stop).'(default)'
            if ($value -and (Test-Path -LiteralPath $value -PathType Leaf)) { return $value }
        } catch { }
    }
    return $null
}

$chrome = Find-Chrome -Configured $ChromePath
if (-not $chrome) {
    Write-Host '[setup_profile] Chrome not found. Install Google Chrome or pass -ChromePath.'
    exit 2
}

if ($env:JG_PROFILES_DIR) {
    $root = $env:JG_PROFILES_DIR
} else {
    $root = Join-Path $env:LOCALAPPDATA 'JGMarketingAgent\profiles'
}
$folder = Join-Path $root ("profile-{0}" -f $Profile)
if (-not (Test-Path -LiteralPath $folder)) {
    New-Item -ItemType Directory -Path $folder | Out-Null
}

$chromeArgs = @("--user-data-dir=$folder", '--no-first-run', '--no-default-browser-check')
if ($WindowPosition) {
    if ($WindowPosition -notmatch '^-?\d+,-?\d+$') {
        Write-Host '[setup_profile] -WindowPosition must look like "x,y", e.g. "-1860,60".'
        exit 2
    }
    $chromeArgs += "--window-position=$WindowPosition"
}
$chromeArgs += 'https://accounts.google.com/'

Write-Host ("[setup_profile] Opening Chrome with profile-{0}" -f $Profile)
Write-Host '  Sign in to Google by hand, check YouTube, then close the Chrome window.'
Start-Process -FilePath $chrome -ArgumentList $chromeArgs
exit 0
