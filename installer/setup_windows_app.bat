@echo off
setlocal

cd /d "%~dp0\.."

echo.
echo === Building A1 Mail Dynamics desktop app ===
call installer\build.bat
if errorlevel 1 (
    echo.
    echo [ERROR] Desktop build failed, so auto-start was not enabled.
    exit /b 1
)

echo.
choice /M "Enable auto-start when you sign in to Windows"
if errorlevel 2 goto :done

echo.
call installer\enable_autostart.bat
if errorlevel 1 exit /b 1

:done
echo.
echo Setup complete.
echo Desktop app: release_dist\A1MailDynamics\A1MailDynamics.exe
echo ZIP file:    release_dist\A1MailDynamics-windows-x64.zip

endlocal
