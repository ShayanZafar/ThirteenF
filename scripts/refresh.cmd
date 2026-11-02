@echo off
rem The recurring update: runs update-data (which skips what is already here), then says what
rem entered and left the Accumulate list since the run before, here and in data\refresh-summary.txt.
rem scripts\schedule-refresh.cmd runs it every day; it never runs beside another update.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup.cmd first.
  exit /b 1
)
".venv\Scripts\python.exe" -m thirteenf.refresh %*
exit /b %errorlevel%
