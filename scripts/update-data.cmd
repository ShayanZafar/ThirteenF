@echo off
rem Downloads any new SEC Form 13F data sets, loads them, rebuilds the model and, with an OpenFIGI
rem key in data\settings.toml, maps new CUSIPs to tickers. The first time, it runs scripts\setup.cmd
rem for you. Double-click it, or run it from a terminal.
rem Pass --no-download to rebuild from the zips already in data\raw.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting ThirteenF up ^(a minute or two^) ...
  echo.
  call "%~dp0setup.cmd"
  if errorlevel 1 goto :failed
  echo.
)
echo Updating the 13F data. The first run downloads about 800 MB and takes about 15 minutes;
echo later runs only fetch new quarters. If the app is open, its pages say the data is being updated until this finishes.
echo.
".venv\Scripts\python.exe" -m thirteenf.ingest %*
if errorlevel 1 goto :failed
echo.
echo Done. The app shows the new data; start it with scripts\start.cmd if it isn't open.
call "%~dp0keep-window.cmd"
exit /b 0

:failed
echo.
echo Something went wrong ^(see above^).
call "%~dp0keep-window.cmd"
exit /b 1
