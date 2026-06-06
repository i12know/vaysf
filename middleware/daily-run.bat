@echo off
setlocal

REM Chrome must already be running in the logged-in desktop session:
REM "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%~dp0temp\chrome-profile"

cd /d "%~dp0" || exit /b 1

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "DATA_DIR=%~dp0data"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python virtual environment not found: %PYTHON_EXE%
    exit /b 1
)

if exist "%DATA_DIR%\individual_application_forms.xlsx" (
    copy /Y "%DATA_DIR%\individual_application_forms.xlsx" "%DATA_DIR%\individual_application_forms-bkup.xlsx" >nul || goto fail
)
if exist "%DATA_DIR%\consent_forms.xlsx" (
    copy /Y "%DATA_DIR%\consent_forms.xlsx" "%DATA_DIR%\consent_forms-bkup.xlsx" >nul || goto fail
)

"%PYTHON_EXE%" chrome_export_vaysf_forms.py || goto fail
"%PYTHON_EXE%" main.py assign-groups --file "%DATA_DIR%\individual_application_forms.xlsx" || goto fail
"%PYTHON_EXE%" main.py sync --type participants || goto fail
"%PYTHON_EXE%" main.py check-consent --file "%DATA_DIR%\consent_forms.xlsx" || goto fail
"%PYTHON_EXE%" main.py sync --type full || goto fail
"%PYTHON_EXE%" main.py sync --type validation || goto fail
"%PYTHON_EXE%" main.py export-church-teams || goto fail
call run-schedule.bat || goto fail

echo [OK] VAYSF nightly run completed successfully.
exit /b 0

:fail
echo [ERROR] VAYSF nightly run stopped with exit code %ERRORLEVEL%.
exit /b 1
