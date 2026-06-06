REM run this first: "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="S:\MyPrj\vay\vaysf\middleware\temp\chrome-profile"
copy "S:\MyPrj\vay\vaysf\middleware\data\individual_application_forms.xlsx" "S:\MyPrj\vay\vaysf\middleware\data\individual_application_forms-bkup.xlsx"
copy "S:\MyPrj\vay\vaysf\middleware\data\consent_forms.xlsx" "S:\MyPrj\vay\vaysf\middleware\data\consent_forms-bkup.xlsx"
cd /d S:\MyPrj\vay\vaysf\middleware
python chrome_export_vaysf_forms.py
python main.py assign-groups --file "S:\MyPrj\vay\vaysf\middleware\data\individual_application_forms.xlsx"
python main.py sync --type participants
python main.py check-consent --file "S:\MyPrj\vay\vaysf\middleware\data\consent_forms.xlsx"
python main.py sync --type full
python main.py sync --type validation
python main.py export-church-teams
run-schedule
