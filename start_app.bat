@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Install the application first using the commands in README.md.
  pause
  exit /b 1
)
echo Opening Oncology Care AI at http://localhost:8501
start "" "http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py
