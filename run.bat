@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 "%SCRIPT_DIR%run.py" --desktop %*
  exit /b %ERRORLEVEL%
)

python "%SCRIPT_DIR%run.py" --desktop %*
exit /b %ERRORLEVEL%
