@echo off
title A1 Mail Dynamics - Production Web Server
color 0A

echo.
echo  =====================================================
echo   A1 Mail Dynamics ^| Production Web Server
echo  =====================================================
echo.

set "PROJECT_ROOT=%~dp0"
set "VENV_DIR=%PROJECT_ROOT%.venv"
set "CLIENT_DIR=%PROJECT_ROOT%client"
set "HOST=127.0.0.1"
set "PORT=5000"

REM ── .env guard ──────────────────────────────────────────────────────────────
if not exist "%PROJECT_ROOT%.env" (
    if exist "%PROJECT_ROOT%.env.example" (
        echo  .env not found -- copying from .env.example
        copy "%PROJECT_ROOT%.env.example" "%PROJECT_ROOT%.env" >nul
        echo.
    ) else (
        echo  [ERROR] .env file is missing. Create it from .env.example.
        pause & exit /b 1
    )
)

REM ── Ensure APP_ENV=production ────────────────────────────────────────────────
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$f='%PROJECT_ROOT%.env'; $t=Get-Content $f -Raw;" ^
  "if ($t -notmatch '(?m)^APP_ENV=production') {" ^
  "  $t = [regex]::Replace($t,'(?m)^APP_ENV=.*','APP_ENV=production');" ^
  "  if ($t -notmatch '(?m)^APP_ENV=') { $t = $t.TrimEnd() + \"`nAPP_ENV=production`n\" };" ^
  "  Set-Content $f $t -NoNewline }"

REM ── Auto-generate FLASK_SECRET_KEY if missing or blank ───────────────────────
for /f "usebackq delims=" %%K in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$f='%PROJECT_ROOT%.env'; $t=Get-Content $f -Raw;" ^
  "$m=[regex]::Match($t,'(?m)^FLASK_SECRET_KEY=(.*)$');" ^
  "if ($m.Success) { $m.Groups[1].Value.Trim() } else { '' }"`) do set "CURRENT_KEY=%%K"

if not defined CURRENT_KEY set "CURRENT_KEY="
set "KEY_LEN=0"
if defined CURRENT_KEY (
    for /f "delims=" %%L in ('powershell -NoProfile -Command "[string]::new('%CURRENT_KEY%').Length"') do set "KEY_LEN=%%L"
)

if %KEY_LEN% LSS 32 (
    for /f "usebackq delims=" %%S in (`python -c "import secrets; print(secrets.token_hex(32))"`) do set "NEW_KEY=%%S"
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$f='%PROJECT_ROOT%.env'; $t=Get-Content $f -Raw;" ^
      "$key='%NEW_KEY%';" ^
      "if ($t -match '(?m)^FLASK_SECRET_KEY=') { $t=[regex]::Replace($t,'(?m)^FLASK_SECRET_KEY=.*',\"FLASK_SECRET_KEY=$key\") } else { $t=$t.TrimEnd()+\"`nFLASK_SECRET_KEY=$key`n\" };" ^
      "Set-Content $f $t -NoNewline"
    echo  Generated a new FLASK_SECRET_KEY.
)

REM ── Python venv ─────────────────────────────────────────────────────────────
echo  [1/4] Setting up Python environment...
if not exist "%VENV_DIR%\Scripts\python.exe" (
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  [ERROR] Could not create venv. Install Python 3.11+.
        pause & exit /b 1
    )
)
call "%VENV_DIR%\Scripts\activate.bat"
pip install --quiet --upgrade pip
pip install --quiet -r "%PROJECT_ROOT%requirements.txt"
if errorlevel 1 (
    echo  [ERROR] pip install failed.
    pause & exit /b 1
)
echo  Python environment ready.

REM ── Frontend build ───────────────────────────────────────────────────────────
echo  [2/4] Building React frontend...
if exist "%CLIENT_DIR%\package-lock.json" (
    call npm --prefix "%CLIENT_DIR%" ci --silent
) else (
    call npm --prefix "%CLIENT_DIR%" install --silent
)
call npm --prefix "%CLIENT_DIR%" run build
if errorlevel 1 (
    echo  [ERROR] Frontend build failed. Install Node.js 18+.
    pause & exit /b 1
)
echo  Frontend build complete.

REM ── Playwright ───────────────────────────────────────────────────────────────
echo  [3/4] Checking Playwright browser...
python -m playwright install chrome 2>nul
if errorlevel 1 python -m playwright install chromium 2>nul

REM ── Start server ─────────────────────────────────────────────────────────────
echo.
echo  [4/4] Starting Waitress production server...
echo.
echo  =====================================================
echo   App URL:  http://%HOST%:%PORT%
echo   Logs:     logs\app.log
echo   Press Ctrl+C to stop.
echo  =====================================================
echo.

ping 127.0.0.1 -n 3 >nul
start "" "http://%HOST%:%PORT%"

set APP_ENV=production
set PYTHONUNBUFFERED=1
python -m app.main
