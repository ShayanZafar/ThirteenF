@echo off
rem Sets up ThirteenF: a Python 3.12 virtual environment in .venv, the app and its
rem dependencies, and data\settings.toml. Safe to run again.
setlocal
cd /d "%~dp0.."

echo ThirteenF setup
echo.

call :find_python
if not defined PYEXE (
  echo Python 3.12 or newer was not found.
  echo Install it from https://www.python.org/downloads/ or run:  winget install Python.Python.3.12
  exit /b 1
)
echo Python: %PYEXE% %PYARGS%

if not exist ".venv\Scripts\python.exe" (
  echo Creating the virtual environment in .venv ...
  "%PYEXE%" %PYARGS% -m venv .venv
  if errorlevel 1 exit /b 1
)
echo Installing ThirteenF and its dependencies ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install --quiet -e ".[dev]"
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -c "from thirteenf.config import ensure_settings_file; print('Settings file:', ensure_settings_file())"

".venv\Scripts\python.exe" -c "import sys; from thirteenf.config import user_setting; sys.exit(0 if user_setting('SEC_USER_AGENT') else 1)"
if errorlevel 1 (
  echo.
  echo SEC_USER_AGENT is not set. The SEC asks every client for a name and contact email:
  echo     setx SEC_USER_AGENT "ThirteenF you@example.com"
  echo Run that once, then open a new terminal.
)
echo.
echo Setup done. Next:
echo   scripts\update-data.cmd   download and load the SEC's 13F data (about 15 minutes the first time)
echo   scripts\start.cmd         open the app at http://127.0.0.1:8000
exit /b 0

:find_python
set "PYEXE="
set "PYARGS="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    set "PYEXE=py"
    set "PYARGS=-3.12"
    exit /b 0
  )
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  exit /b 0
)
where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "PYEXE=python"
    exit /b 0
  )
)
exit /b 0
