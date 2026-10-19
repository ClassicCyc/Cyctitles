@echo off
rem Run Cyctitles from the local virtual environment (developer mode).
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Create it first:
  echo   uv venv --python 3.12 .venv
  echo   uv pip install --python .venv\Scripts\python.exe -r requirements.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py
