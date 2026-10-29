@echo off
title A1 Mail Dynamics - Web Dev Mode
color 0B

echo.
echo  =====================================================
echo   A1 Mail Dynamics ^| Web Development Starter
echo  =====================================================
echo.

set "PROJECT_ROOT=%~dp0"
set "VENV_DIR=%PROJECT_ROOT%.venv"
set "CLIENT_DIR=%PROJECT_ROOT%client"

REM ── Create venv if missing ─────────────────────────────────────────────────
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo  Creating Python virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  [ERROR] Could not create venv. Make sure Python 3.11+ is installed.
        pause & exit /b 1
    )
)

REM ── Install Python dependencies ────────────────────────────────────────────
echo  Installing Python dependencies...
call "%VENV_DIR%\Scripts\activate.bat"
pip install --quiet --upgrade pip
pip install --quiet -r "%PROJECT_ROOT%requirements.txt"
if errorlevel 1 (
    echo  [ERROR] pip install failed.
    pause & exit /b 1
)

REM ── Playwright browser ─────────────────────────────────────────────────────
echo  Checking Playwright browser...
python -m playwright install chrome 2>nul
if errorlevel 1 python -m playwright install chromium 2>nul

REM ── Node dependencies ──────────────────────────────────────────────────────
echo  Installing Node dependencies...
if exist "%CLIENT_DIR%\package-lock.json" (
    call npm --prefix "%CLIENT_DIR%" ci --silent
) else (
    call npm --prefix "%CLIENT_DIR%" install --silent
)

REM ── Copy .env if missing ───────────────────────────────────────────────────
if not exist "%PROJECT_ROOT%.env" (
    if exist "%PROJECT_ROOT%.env.example" (
        echo  .env not found — copying from .env.example
        copy "%PROJECT_ROOT%.env.example" "%PROJECT_ROOT%.env" >nul
    )
)

echo.
echo  Starting Flask backend on http://127.0.0.1:5000 ...
start "A1 Flask Backend" cmd /k "cd /d "%PROJECT_ROOT%" && call .\.venv\Scripts\activate.bat && set PYTHONUNBUFFERED=1 && python -m app.main"

echo  Starting Vite dev server on http://localhost:5173 ...
start "A1 Vite Frontend" cmd /k "cd /d "%CLIENT_DIR%" && npm run dev"

echo.
echo  Waiting for servers to start...
ping 127.0.0.1 -n 4 >nul

echo  Opening browser...
start "" "http://localhost:5173"

echo.
echo  =====================================================
echo   Frontend (hot-reload):  http://localhost:5173
echo   Backend API:            http://127.0.0.1:5000
echo  =====================================================
echo.
echo  Close the "A1 Flask Backend" and "A1 Vite Frontend"
echo  windows to stop both servers.
echo.
pause
