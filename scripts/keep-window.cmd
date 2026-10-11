@echo off
rem The other scripts call this last. When a script was started with a double-click (so its
rem window is Explorer's and closes when it ends), this waits for a key press, so what the
rem script printed can be read. From a terminal or another program, it returns at once.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$window = Get-CimInstance Win32_Process -Filter ('ProcessId=' + (Get-CimInstance Win32_Process -Filter ('ProcessId=' + $PID)).ParentProcessId); $opener = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $window.ParentProcessId); exit [int]($opener.Name -eq 'explorer.exe')"
if errorlevel 1 pause
exit /b 0
