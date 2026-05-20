@echo off
setlocal
REM ============================================================
REM  run-consent-404-investigation.bat
REM
REM  Investigates consent-check 404 cases from the latest
REM  sportsfest log and writes data\consent_404_investigation.xlsx
REM
REM  Run from the middleware\ folder:
REM      run-consent-404-investigation.bat
REM
REM  Optional explicit log file:
REM      run-consent-404-investigation.bat --log-file "S:\path\to\sportsfest_20260519.log"
REM ============================================================

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

REM This diagnostic does not need the normal shared export location.
REM Force a local export dir so it still runs if the shared drive is unavailable.
set "EXPORT_DIR=%CD%\data"

echo.
echo ============================================================
echo  investigate-consent-404s
echo ============================================================
echo  Python: %PYTHON_EXE%
echo  Export: %EXPORT_DIR%
echo.

%PYTHON_EXE% main.py investigate-consent-404s %*
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% == 0 (
    echo  [OK] Investigation finished. Check data\consent_404_investigation.xlsx
) else (
    echo  [ERROR] Investigation failed with exit code %EXIT_CODE%.
    echo          Check the log output above for details.
)
echo.
exit /b %EXIT_CODE%
