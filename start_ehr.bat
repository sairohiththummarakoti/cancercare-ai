@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Set up Python first using the commands in EHR_SETUP.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\run_ehr.py"
if errorlevel 1 pause
