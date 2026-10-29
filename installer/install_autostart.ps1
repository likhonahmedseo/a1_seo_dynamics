# ─────────────────────────────────────────────────────────────────────────────
#  install_autostart.ps1
#  Adds a shortcut to A1MailDynamics.exe to the current user's Startup folder
#  so the app launches in the background every time Windows boots.
#
#  Usage from project root:
#      powershell -ExecutionPolicy Bypass -File installer\install_autostart.ps1
#
#  No admin rights required — this only touches the per-user Startup folder.
# ─────────────────────────────────────────────────────────────────────────────
[CmdletBinding()]
param(
    [string]$ExePath = "",
    [switch]$NoMinimize
)

$ErrorActionPreference = 'Stop'

# ── Resolve the .exe path ───────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir '..')

if (-not $ExePath) {
    $candidates = @(
        Join-Path $ProjectRoot 'dist\A1MailDynamics\A1MailDynamics.exe'
        Join-Path $ProjectRoot 'A1MailDynamics.exe'
    )
    $ExePath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $ExePath -or -not (Test-Path $ExePath)) {
    Write-Host ""
    Write-Host "[ERROR] Could not find A1MailDynamics.exe." -ForegroundColor Red
    Write-Host "Build it first with:  installer\build.bat" -ForegroundColor Yellow
    Write-Host "Or pass the path explicitly:" -ForegroundColor Yellow
    Write-Host '    .\install_autostart.ps1 -ExePath "C:\path\to\A1MailDynamics.exe"' -ForegroundColor Yellow
    exit 1
}

$ExePath = (Resolve-Path $ExePath).Path

# ── Build the shortcut ──────────────────────────────────────────────────────
$Startup      = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $Startup 'A1 Mail Dynamics.lnk'

$WS  = New-Object -ComObject WScript.Shell
$Lnk = $WS.CreateShortcut($ShortcutPath)
$Lnk.TargetPath       = $ExePath
$Lnk.WorkingDirectory = Split-Path $ExePath
$Lnk.Description      = 'A1 Mail Dynamics — AI Marketing Agent'

if ($NoMinimize) {
    $Lnk.Arguments   = ''
    $Lnk.WindowStyle = 1   # Normal
} else {
    $Lnk.Arguments   = '--background'
    $Lnk.WindowStyle = 7   # Minimized
}

$Lnk.Save()

# ── Done ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Auto-start enabled." -ForegroundColor Green
Write-Host "  A1 Mail Dynamics will launch every time you sign in to Windows."
Write-Host ""
Write-Host "  Shortcut:  $ShortcutPath"
Write-Host "  Target:    $ExePath"
Write-Host "  Arguments: $($Lnk.Arguments)"
Write-Host ""
Write-Host "  To disable, run:  .\installer\uninstall_autostart.ps1" -ForegroundColor Yellow
Write-Host ""
