@echo off
rem Starts ThirteenF at http://127.0.0.1:8000 and opens it in your browser.
rem Options: --port 8001 to use another port, --reload while changing the code.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup.cmd first.
  exit /b 1
)
if not exist "data\thirteenf.duckdb" (
  echo There is no data yet: run scripts\update-data.cmd first. The app will say so too.
)
".venv\Scripts\python.exe" -m thirteenf.web --open %*
