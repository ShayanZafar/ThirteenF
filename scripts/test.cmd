@echo off
rem Runs the tests. Tests that need the SEC data skip until it is loaded.
rem Pass pytest options through, for example: scripts\test.cmd -k tickers
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup.cmd first.
  exit /b 1
)
".venv\Scripts\python.exe" -m pytest %*
