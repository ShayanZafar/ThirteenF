@echo off
rem Registers scripts\refresh.cmd with Windows Task Scheduler to run every day at 07:00 (pass
rem another time, for example: scripts\schedule-refresh.cmd 18:30). It runs only while you are
rem signed in, as you, so it finds SEC_USER_AGENT and data\settings.toml as update-data does.
rem Remove it with: schtasks /Delete /TN "ThirteenF refresh" /F
setlocal
cd /d "%~dp0.."
set "AT=%~1"
if "%AT%"=="" set "AT=07:00"
schtasks /Create /TN "ThirteenF refresh" /TR "\"%CD%\scripts\refresh.cmd\"" /SC DAILY /ST %AT% /F
if errorlevel 1 (
  echo Could not register the task ^(see above^).
  call "%~dp0keep-window.cmd"
  exit /b 1
)
echo ThirteenF will refresh every day at %AT%. The latest summary is in data\refresh-summary.txt.
call "%~dp0keep-window.cmd"
