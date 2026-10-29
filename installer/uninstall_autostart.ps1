# ─────────────────────────────────────────────────────────────────────────────
#  uninstall_autostart.ps1
#  Removes the Startup-folder shortcut created by install_autostart.ps1.
#
#  Usage from project root:
#      powershell -ExecutionPolicy Bypass -File installer\uninstall_autostart.ps1
# ─────────────────────────────────────────────────────────────────────────────
$ErrorActionPreference = 'Stop'

$Startup      = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $Startup 'A1 Mail Dynamics.lnk'

if (Test-Path $ShortcutPath) {
    Remove-Item -Path $ShortcutPath -Force
    Write-Host ""
    Write-Host "  Auto-start removed." -ForegroundColor Green
    Write-Host "  A1 Mail Dynamics will no longer launch when Windows starts."
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "  Auto-start was not enabled (no shortcut found at):" -ForegroundColor Yellow
    Write-Host "  $ShortcutPath"
    Write-Host ""
}
