@echo off
title A1 Mail Dynamics - AI Agent
color 0A

echo.
echo  ===========================================
echo   A1 Mail Dynamics - Marketing Automation
echo  ===========================================
echo.

REM ── Check Node.js and build frontend if needed ────────────────────────────
if not exist "%~dp0client\dist" (
    echo  First-time setup: Building the frontend - this takes a minute...
    cd /d "%~dp0client"
    call npm install
    call npm run build
    cd /d "%~dp0"
    echo  Frontend build complete.
    echo.
)

REM ── Install / update Python dependencies ──────────────────────────────────
echo  Checking Python dependencies...
if not exist "%~dp0.venv" (
    echo  Creating Python virtual environment...
    python -m venv .venv
)
call "%~dp0.venv\Scripts\activate.bat"
pip install -r "%~dp0requirements.txt" -q
if errorlevel 1 (
  echo  ERROR: pip install failed. Make sure Python is installed.
  pause & exit /b 1
)

REM ── Install Playwright Chrome browser if not already installed ─────────────
echo  Checking internal Chrome browser...
python -m playwright install chrome 2>nul
if errorlevel 1 (
  python -m playwright install chromium
)
echo  Browser automation ready.
echo.

REM ── Start Production Server (Waitress) ─────────────────────────────────────
echo  Starting A1 Marketing App on port 5000...
echo.
set PYTHONUNBUFFERED=1

:: Open a new window for the server
start "A1 Server" cmd /k "cd /d "%~dp0" && set PYTHONUNBUFFERED=1 && call .\.venv\Scripts\activate.bat && python -m app.main"

echo  Waiting for server to start...
ping 127.0.0.1 -n 4 >nul

REM ── Open browser ──────────────────────────────────────────────────────────
echo  Opening browser...
start "" "http://127.0.0.1:5000"

echo.
echo  ✓ System is running!
echo  ─────────────────────────────────────────
echo  App URL: http://127.0.0.1:5000
echo  ─────────────────────────────────────────
echo  IMPORTANT for Gmail automation mode:
echo  You must close ALL standard Chrome windows 
echo  before clicking "Send via Gmail Automation"
echo  ─────────────────────────────────────────
echo.
echo  (You can close this black window if the app is still open in the A1 Server window)
echo.
pause
