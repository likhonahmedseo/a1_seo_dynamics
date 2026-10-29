@echo off
REM ============================================================================
REM A1 Mail Dynamics - Customer License Generator
REM ============================================================================
REM HOW MACHINE-BOUND LICENSES WORK
REM   Machine-bound licenses (options 2, 3, 4) are tied to the customer's PC.
REM   To get the customer's Machine ID:
REM     Option A: Customer opens the app → reaches the License screen → clicks
REM               "Copy Machine ID" → sends the ID to you.
REM     Option B: Customer runs:  python tools\get_machine_id.py
REM               (or visit http://localhost:5000/api/license/machine-id while
REM               the app is running on their machine)
REM   Universal licenses (option 1, 5) use machine_id=* and work on any PC.
REM ============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo.
echo ========================================================================
echo   A1 Mail Dynamics - Customer License Generator
echo ========================================================================
echo.

if not exist "private\vendor-license-private.pem" (
    echo ERROR: Private key not found at private\vendor-license-private.pem
    echo.
    echo Run this first to generate your vendor keypair:
    echo   .\.venv\Scripts\python.exe tools\generate_license_keys.py ^
    echo       --private-key private\vendor-license-private.pem
    echo.
    pause
    exit /b 1
)

echo Enter customer details:
echo.
set /p CUSTOMER_NAME="Customer/Company Name: "
if "!CUSTOMER_NAME!"=="" (
    echo ERROR: Customer name is required.
    pause
    exit /b 1
)

set /p CUSTOMER_EMAIL="Customer Email: "
if "!CUSTOMER_EMAIL!"=="" (
    echo ERROR: Customer email is required.
    pause
    exit /b 1
)

echo.
echo ------------------------------------------------------------------------
echo License Plans
echo   [1] 7-Day Trial               - any machine, expires after 7 days
echo   [2] 30-Day Subscription       - machine-bound, renewable monthly
echo   [3] 1-Year Subscription       - machine-bound, renewable yearly
echo   [4] Perpetual Lifetime        - machine-bound, one-time purchase
echo   [5] Universal (any machine)   - no machine lock, use for floating seats
echo ------------------------------------------------------------------------
echo.
echo   For options 2-4 you will need the customer's Machine ID.
echo   The customer can find it by:
echo     - Opening the app and clicking "Copy Machine ID" on the License screen
echo     - Or running:  python tools\get_machine_id.py  on their machine
echo     - Or visiting: http://localhost:5000/api/license/machine-id (app running)
echo.
set /p LICENSE_OPTION="Choose option (1-5): "

if /i "!LICENSE_OPTION!"=="1" goto :trial_license
if /i "!LICENSE_OPTION!"=="2" goto :monthly_license
if /i "!LICENSE_OPTION!"=="3" goto :yearly_license
if /i "!LICENSE_OPTION!"=="4" goto :perpetual_license
if /i "!LICENSE_OPTION!"=="5" goto :universal_license

echo ERROR: Invalid option. Please choose 1, 2, 3, 4, or 5.
pause
exit /b 1

:require_machine_id
echo.
echo The customer's Machine ID is shown on the License screen in the app.
echo It can also be retrieved by visiting:
echo   http://localhost:5000/api/license/machine-id  (while app runs on their PC)
echo Or by running on their PC:
echo   python tools\get_machine_id.py
echo.
set /p MACHINE_ID="Paste customer's Machine ID (32 hex chars): "
if "!MACHINE_ID!"=="" (
    echo ERROR: Machine ID is required for this license type.
    pause
    exit /b 1
)
REM Trim to 32 chars and uppercase
set "MACHINE_ID=!MACHINE_ID:~0,32!"
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "('!MACHINE_ID!').ToUpper()"`) do set "MACHINE_ID=%%i"
if "!MACHINE_ID!"=="" (
    echo ERROR: Machine ID could not be processed.
    pause
    exit /b 1
)
echo Using Machine ID: !MACHINE_ID!
goto :eof

:trial_license
echo.
echo Creating 7-day trial license (works on any machine)
set "MACHINE_ID=*"
set "LICENSE_TYPE=7-Day Trial"
set "DURATION_DAYS=7"
set "DESC=7-Day Trial (any machine)"
set "RENEWAL_NOTE=Issue a fresh trial key if you want to extend the demo."
goto :generate_license

:monthly_license
call :require_machine_id
echo.
echo Creating 30-day subscription license for machine !MACHINE_ID!
set "LICENSE_TYPE=30-Day Subscription"
set "DURATION_DAYS=30"
set "DESC=30-Day Subscription (bound to !MACHINE_ID!)"
set "RENEWAL_NOTE=To renew, generate a new 30-day key for the same Machine ID and send it to the customer."
goto :generate_license

:yearly_license
call :require_machine_id
echo.
echo Creating 1-year subscription license for machine !MACHINE_ID!
set "LICENSE_TYPE=1-Year Subscription"
set "DURATION_DAYS=365"
set "DESC=1-Year Subscription (bound to !MACHINE_ID!)"
set "RENEWAL_NOTE=To renew, generate a new 1-year key for the same Machine ID and send it to the customer."
goto :generate_license

:perpetual_license
call :require_machine_id
echo.
echo Creating perpetual lifetime license for machine !MACHINE_ID!
set "LICENSE_TYPE=Perpetual Lifetime"
set "DURATION_DAYS=0"
set "DESC=Perpetual Lifetime (bound to !MACHINE_ID!)"
set "RENEWAL_NOTE=No expiry. Reissue only if the customer changes machine (new machine_id)."
goto :generate_license

:universal_license
echo.
echo Creating universal license (any machine, no expiry)
set "MACHINE_ID=*"
set "LICENSE_TYPE=Universal License"
set "DURATION_DAYS=0"
set "DESC=Universal License (any machine, no expiry)"
set "RENEWAL_NOTE=This license works on any machine. Issue a new one if you want to revoke access."
goto :generate_license

:generate_license
echo.
echo ------------------------------------------------------------------------
echo Generating license...
echo ------------------------------------------------------------------------

if "!DURATION_DAYS!"=="0" (
    .\.venv\Scripts\python.exe tools\generate_license_token.py ^
        --private-key private\vendor-license-private.pem ^
        --customer-name "!CUSTOMER_NAME!" ^
        --customer-email "!CUSTOMER_EMAIL!" ^
        --machine-id "!MACHINE_ID!" ^
        --license-type "!LICENSE_TYPE!" > temp_token.txt 2>&1
) else (
    .\.venv\Scripts\python.exe tools\generate_license_token.py ^
        --private-key private\vendor-license-private.pem ^
        --customer-name "!CUSTOMER_NAME!" ^
        --customer-email "!CUSTOMER_EMAIL!" ^
        --machine-id "!MACHINE_ID!" ^
        --license-type "!LICENSE_TYPE!" ^
        --duration-days !DURATION_DAYS! > temp_token.txt 2>&1
)

if !errorlevel! neq 0 (
    echo.
    echo ERROR generating license:
    type temp_token.txt
    del temp_token.txt
    pause
    exit /b 1
)

set /p LICENSE_TOKEN=<temp_token.txt
del temp_token.txt

set "PLAN_SLUG=!LICENSE_TYPE: =_!"
set "PLAN_SLUG=!PLAN_SLUG:-=_!"
set "FILENAME=!CUSTOMER_NAME: =_!_!PLAN_SLUG!"
set "FILENAME=!FILENAME:,=!"
if not exist "private\licenses" mkdir "private\licenses"
(
echo Customer Name: !CUSTOMER_NAME!
echo Customer Email: !CUSTOMER_EMAIL!
echo License Type: !DESC!
echo Machine ID: !MACHINE_ID!
echo Generated: %date% %time%
echo Renewal: !RENEWAL_NOTE!
echo.
echo ACTIVATION KEY:
echo !LICENSE_TOKEN!
) > "private\licenses\!FILENAME!_License.txt"

echo.
echo ========================================================================
echo   LICENSE GENERATED SUCCESSFULLY
echo ========================================================================
echo.
echo Customer: !CUSTOMER_NAME!
echo Email:    !CUSTOMER_EMAIL!
echo Type:     !DESC!
echo Machine:  !MACHINE_ID!
echo Renewal:  !RENEWAL_NOTE!
echo.
echo ------------------------------------------------------------------------
echo ACTIVATION KEY (paste this into the app's License screen)
echo ------------------------------------------------------------------------
echo !LICENSE_TOKEN!
echo ------------------------------------------------------------------------
echo.
echo Saved to: private\licenses\!FILENAME!_License.txt
echo.
echo How to activate on the customer's machine:
echo   1. Customer opens A1 Mail Dynamics on their PC
echo   2. Customer reaches the License Activation screen
echo   3. Customer pastes the activation key above into the token field
echo   4. Customer clicks "Activate License"
echo.

echo !LICENSE_TOKEN! | clip
echo Activation key copied to clipboard!
echo.

pause
endlocal
