@echo off
rem Runs one ThirteenF command with the app's own Python in .venv, never another Python on PATH
rem (a bare "python -m thirteenf.tickers" can start an old Python and fail with "No module named").
rem   scripts\run.cmd tickers --retry-missing
rem   scripts\run.cmd prices
rem Commands: ingest, refresh, model, prices, tickers, web. With none, it lists them.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup.cmd first.
  exit /b 1
)
".venv\Scripts\python.exe" -m thirteenf %*
exit /b %errorlevel%
