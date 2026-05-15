@echo off
setlocal
REM ============================================================
REM  run-schedule.bat
REM  Step 1: solve-schedule  (CP-SAT solver)
REM  Step 2: produce-schedule (Excel renderer)
REM
REM  Run from the middleware\ folder:
REM      run-schedule.bat
REM
REM  Optional overrides (set before running or pass inline):
REM      set SCHEDULE_SOLVER_TIMEOUT=60
REM      set EXPORT_DIR=G:\Shared drives\...\VAYSF-data
REM ============================================================

if not defined EXPORT_DIR (
    if exist ".env" (
        for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
            if /I "%%A"=="EXPORT_DIR" set "EXPORT_DIR=%%B"
        )
    )
)

if defined EXPORT_DIR (
    set "EXPORT_DIR=%EXPORT_DIR:"=%"
    set "SCHEDULE_INPUT_PATH=%EXPORT_DIR%\schedule_input.json"
    set "SCHEDULE_OUTPUT_PATH=%EXPORT_DIR%\schedule_output.json"
) else (
    set "SCHEDULE_INPUT_PATH=%CD%\data\schedule_input.json"
    set "SCHEDULE_OUTPUT_PATH=%CD%\data\schedule_output.json"
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo.
echo ============================================================
echo  STEP 1 - solve-schedule
echo ============================================================
echo  Input : %SCHEDULE_INPUT_PATH%
echo  Output: %SCHEDULE_OUTPUT_PATH%
echo  Python: %PYTHON_EXE%

if not exist "%SCHEDULE_INPUT_PATH%" (
    echo  [ERROR] schedule_input.json was not found at:
    echo          %SCHEDULE_INPUT_PATH%
    echo          Run export-church-teams first, or set EXPORT_DIR correctly.
    set SOLVE_CODE=3
    goto after_solve
)

%PYTHON_EXE% main.py solve-schedule --input "%SCHEDULE_INPUT_PATH%" --output "%SCHEDULE_OUTPUT_PATH%"
set SOLVE_CODE=%ERRORLEVEL%

:after_solve
echo.
echo  Exit code: %SOLVE_CODE%

if %SOLVE_CODE% == 0 (
    echo  [OK] All games scheduled successfully.
    goto produce
)

if %SOLVE_CODE% == 1 (
    echo  [WARN] Some games could not be scheduled.
    echo         Check the log above for which games were dropped
    echo         and verify their resource_type matches a resource
    echo         in schedule_input.json.
    echo         Continuing to produce-schedule so you can review
    echo         the partial results...
    goto produce
)

if %SOLVE_CODE% == 2 (
    echo  [TIMEOUT] The solver ran out of time before finding a solution.
    echo            This does NOT mean the schedule is impossible.
    echo            Try increasing the timeout and re-running:
    echo                set SCHEDULE_SOLVER_TIMEOUT=120
    echo                run-schedule.bat
    goto end
)

if %SOLVE_CODE% == 3 (
    echo  [ERROR] A hard error occurred - bad input file, invalid JSON,
    echo          or ortools is not installed.
    echo          Check the log above for details.
    goto end
)

echo  [UNKNOWN] Unexpected exit code: %SOLVE_CODE%
goto end

:produce
echo.
echo ============================================================
echo  STEP 2 - produce-schedule
echo ============================================================
%PYTHON_EXE% main.py produce-schedule --input "%SCHEDULE_OUTPUT_PATH%" --constraint "%SCHEDULE_INPUT_PATH%"
set PRODUCE_CODE=%ERRORLEVEL%

echo.
if %PRODUCE_CODE% == 0 (
    echo  [OK] Schedule Excel written to the EXPORT_DIR.
) else (
    echo  [ERROR] produce-schedule failed with exit code %PRODUCE_CODE%.
    echo          Check the log above for details.
)

:end
echo.
echo ============================================================
echo  solve-schedule : exit %SOLVE_CODE%
if defined PRODUCE_CODE (
    echo  produce-schedule: exit %PRODUCE_CODE%
)
echo ============================================================
echo.
