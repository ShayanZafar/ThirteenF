@echo off
rem Starts ThirteenF at http://127.0.0.1:8000 and opens it in your browser. The first time, it runs
rem scripts\setup.cmd for you (Python 3.12 or newer must be installed). Double-click it, or run it
rem from a terminal. Options: --port 8001 to use another port, --reload while changing the code.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting ThirteenF up ^(a minute or two^) ...
  echo.
  call "%~dp0setup.cmd"
  if errorlevel 1 goto :failed
  echo.
)
if not exist "data\thirteenf.duckdb" (
  echo There is no data yet: run scripts\update-data.cmd first. The app will say so too.
)
".venv\Scripts\python.exe" -m thirteenf.web --open %*
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Something went wrong ^(see above^).
call "%~dp0keep-window.cmd"
exit /b 1
