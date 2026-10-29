@echo off
setlocal

set "APP_DIR=%~dp0"

if not exist "%APP_DIR%A1MailDynamics.exe" (
    echo.
    echo [ERROR] A1MailDynamics.exe was not found beside this launcher.
    echo Keep this file in the same folder as A1MailDynamics.exe.
    exit /b 1
)

start "" "%APP_DIR%A1MailDynamics.exe"

endlocal
