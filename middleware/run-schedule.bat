@echo off
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
REM ============================================================

echo.
echo ============================================================
echo  STEP 1 — solve-schedule
echo ============================================================
python main.py solve-schedule
set SOLVE_CODE=%ERRORLEVEL%

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
    echo  [ERROR] A hard error occurred — bad input file, invalid JSON,
    echo          or ortools is not installed.
    echo          Check the log above for details.
    goto end
)

echo  [UNKNOWN] Unexpected exit code: %SOLVE_CODE%
goto end

:produce
echo.
echo ============================================================
echo  STEP 2 — produce-schedule
echo ============================================================
python main.py produce-schedule
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
