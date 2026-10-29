@echo off
setlocal
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe
  exit /b 1
)

".\.venv\Scripts\python.exe" tools\generate_license_keys.py --private-key private\vendor-license-private.pem
endlocal
