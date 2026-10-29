@echo off
setlocal

cd /d "%~dp0\.."

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH. Install Python 3.11+ first.
    exit /b 1
)

python installer\build.py --platform windows
exit /b %errorlevel%
