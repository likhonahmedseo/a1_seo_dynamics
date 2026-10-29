@echo off
setlocal

set "APP_DIR=%~dp0"
set "PORT=5174"
set "URL="

rem Check for an already-running instance before starting a new one
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$appDir = [System.IO.Path]::GetFullPath('%APP_DIR%');" ^
  "$runtimeFile = Join-Path $appDir 'data\runtime\active_server.json';" ^
  "$candidates = New-Object System.Collections.Generic.List[string];" ^
  "if (Test-Path $runtimeFile) {" ^
  "  try { $state = Get-Content $runtimeFile -Raw | ConvertFrom-Json; if ($state.url) { [void]$candidates.Add([string]$state.url) } } catch {}" ^
  "}" ^
  "[void]$candidates.Add('http://127.0.0.1:%PORT%');" ^
  "$seen = @{};" ^
  "foreach ($candidate in $candidates) {" ^
  "  if (-not $candidate -or $seen.ContainsKey($candidate)) { continue }" ^
  "  $seen[$candidate] = $true;" ^
  "  try {" ^
  "    $resp = Invoke-RestMethod -Uri ($candidate + '/api/health') -TimeoutSec 2;" ^
  "    if ($resp.ok) { Write-Output $candidate; exit 0 }" ^
  "  } catch {}" ^
  "}"`) do set "URL=%%I"
if defined URL goto :open

if exist "%APP_DIR%A1MailDynamics.exe" goto :packaged
if exist "%APP_DIR%\.venv\Scripts\python.exe" goto :source

echo.
echo [ERROR] Could not find A1MailDynamics.exe or a local Python environment.
echo Place this file beside A1MailDynamics.exe, or run it from the project root.
exit /b 1

:packaged
echo.
echo Opening A1 Mail Dynamics in your browser...
start "A1 Mail Dynamics Server" /min "%APP_DIR%A1MailDynamics.exe" --no-window --port %PORT%
goto :wait_for_server

:source
echo.
echo Opening A1 Mail Dynamics from the project source in your browser...
start "A1 Mail Dynamics Server" /min "%APP_DIR%\.venv\Scripts\python.exe" -m app.desktop --no-window --port %PORT%
goto :wait_for_server

:wait_for_server
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$appDir = [System.IO.Path]::GetFullPath('%APP_DIR%');" ^
  "$runtimeFile = Join-Path $appDir 'data\runtime\active_server.json';" ^
  "$fallback = 'http://127.0.0.1:%PORT%';" ^
  "for ($i = 0; $i -lt 40; $i++) {" ^
  "  $candidates = New-Object System.Collections.Generic.List[string];" ^
  "  [void]$candidates.Add($fallback);" ^
  "  if (Test-Path $runtimeFile) {" ^
  "    try { $state = Get-Content $runtimeFile -Raw | ConvertFrom-Json; if ($state.url) { [void]$candidates.Add([string]$state.url) } } catch {}" ^
  "  }" ^
  "  $seen = @{};" ^
  "  foreach ($candidate in $candidates) {" ^
  "    if (-not $candidate -or $seen.ContainsKey($candidate)) { continue }" ^
  "    $seen[$candidate] = $true;" ^
  "    try {" ^
  "      $resp = Invoke-RestMethod -Uri ($candidate + '/api/health') -TimeoutSec 2;" ^
  "      if ($resp.ok) { Write-Output $candidate; exit 0 }" ^
  "    } catch {}" ^
  "  }" ^
  "  Start-Sleep -Milliseconds 500;" ^
  "}"`) do set "URL=%%I"

if not defined URL (
    echo.
    echo [ERROR] Browser mode could not detect a healthy local app server.
    echo Try Open Desktop App.bat first, then run this launcher again.
    exit /b 1
)

echo.
echo If the page does not load immediately, wait a few seconds and refresh:
echo   %URL%

:open
start "" "%URL%"

endlocal
