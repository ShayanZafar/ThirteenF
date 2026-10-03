@echo off
rem Downloads any new SEC Form 13F data sets, loads them, rebuilds the model and,
rem with an OpenFIGI key in data\settings.toml, maps new CUSIPs to tickers.
rem Pass --no-download to rebuild from the zips already in data\raw.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup.cmd first.
  exit /b 1
)
echo Updating the 13F data. The first run downloads about 800 MB and takes about 15 minutes;
echo later runs only fetch new quarters. If the app is open, its pages say the data is being updated until this finishes.
echo.
".venv\Scripts\python.exe" -m thirteenf.ingest %*
