@echo off
setlocal

REM run this first: "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="S:\MyPrj\vay\vaysf\middleware\temp\chrome-profile"
cd /d S:\MyPrj\vay\vaysf\middleware

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found at %CD%\.venv
    exit /b 1
)
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

if not defined EXPORT_DIR (
    if exist ".env" (
        for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
            if /I "%%A"=="EXPORT_DIR" set "EXPORT_DIR=%%B"
        )
    )
)
if defined EXPORT_DIR set "EXPORT_DIR=%EXPORT_DIR:"=%"
if defined EXPORT_DIR (
    set "SCHEDULE_INPUT_PATH=%EXPORT_DIR%\schedule_input.json"
) else (
    set "SCHEDULE_INPUT_PATH=%CD%\data\schedule_input.json"
)

copy /Y "S:\MyPrj\vay\vaysf\middleware\data\individual_application_forms.xlsx" "S:\MyPrj\vay\vaysf\middleware\data\individual_application_forms-bkup.xlsx" || goto failed
copy /Y "S:\MyPrj\vay\vaysf\middleware\data\consent_forms.xlsx" "S:\MyPrj\vay\vaysf\middleware\data\consent_forms-bkup.xlsx" || goto failed
"%PYTHON_EXE%" chrome_export_vaysf_forms.py
if errorlevel 1 goto failed
"%PYTHON_EXE%" main.py assign-groups --file "S:\MyPrj\vay\vaysf\middleware\data\individual_application_forms.xlsx"
if errorlevel 1 goto failed
"%PYTHON_EXE%" main.py sync --type participants
if errorlevel 1 echo [WARN] Initial participant sync reported errors; the full sync will retry them.
"%PYTHON_EXE%" main.py check-consent --file "S:\MyPrj\vay\vaysf\middleware\data\consent_forms.xlsx"
if errorlevel 1 echo [WARN] check-consent reported errors (e.g. known ChMeetings 404s); continuing.
"%PYTHON_EXE%" main.py sync --type full
if errorlevel 1 goto failed
"%PYTHON_EXE%" main.py sync --type validation
if errorlevel 1 goto failed

for /f %%I in ('powershell -NoProfile -Command "if (Test-Path -LiteralPath $env:SCHEDULE_INPUT_PATH) { (Get-Item -LiteralPath $env:SCHEDULE_INPUT_PATH).LastWriteTimeUtc.Ticks } else { 0 }"') do set "SCHEDULE_INPUT_BEFORE=%%I"
"%PYTHON_EXE%" main.py export-church-teams
if errorlevel 1 goto failed
for /f %%I in ('powershell -NoProfile -Command "if (Test-Path -LiteralPath $env:SCHEDULE_INPUT_PATH) { (Get-Item -LiteralPath $env:SCHEDULE_INPUT_PATH).LastWriteTimeUtc.Ticks } else { 0 }"') do set "SCHEDULE_INPUT_AFTER=%%I"
if "%SCHEDULE_INPUT_AFTER%"=="0" (
    echo [ERROR] export-church-teams did not create schedule_input.json at:
    echo         %SCHEDULE_INPUT_PATH%
    goto failed
)
if "%SCHEDULE_INPUT_AFTER%"=="%SCHEDULE_INPUT_BEFORE%" (
    echo [ERROR] export-church-teams did not refresh schedule_input.json.
    echo         Refusing to solve a stale schedule input:
    echo         %SCHEDULE_INPUT_PATH%
    goto failed
)

call run-schedule.bat
exit /b %ERRORLEVEL%

:failed
echo [ERROR] daily-run.bat stopped because a required step failed.
exit /b 1
