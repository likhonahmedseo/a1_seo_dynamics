@echo off
setlocal

cd /d "%~dp0\.."
powershell -ExecutionPolicy Bypass -File "installer\uninstall_autostart.ps1" %*

endlocal
