@echo off
setlocal

REM run this first: "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="S:\MyPrj\vay\vaysf\middleware\temp\chrome-profile"
cd /d S:\MyPrj\vay\vaysf\middleware

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found at %CD%\.venv
    exit /b 1
)
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

copy /Y "S:\MyPrj\vay\vaysf\middleware\data\individual_application_forms.xlsx" "S:\MyPrj\vay\vaysf\middleware\data\individual_application_forms-bkup.xlsx"
copy /Y "S:\MyPrj\vay\vaysf\middleware\data\consent_forms.xlsx" "S:\MyPrj\vay\vaysf\middleware\data\consent_forms-bkup.xlsx"
"%PYTHON_EXE%" chrome_export_vaysf_forms.py
"%PYTHON_EXE%" main.py assign-groups --file "S:\MyPrj\vay\vaysf\middleware\data\individual_application_forms.xlsx"
"%PYTHON_EXE%" main.py sync --type participants
"%PYTHON_EXE%" main.py check-consent --file "S:\MyPrj\vay\vaysf\middleware\data\consent_forms.xlsx"
"%PYTHON_EXE%" main.py sync --type full
"%PYTHON_EXE%" main.py sync --type validation
"%PYTHON_EXE%" main.py export-church-teams
call run-schedule
