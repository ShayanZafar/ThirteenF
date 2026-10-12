@echo off
rem The one check before a change is done. You, Claude and CI all run this.
rem Formatting, lint, types, licences, the tests, the core flows map, then the size and scope of Claude's
rem instruction files. Tests that need the SEC data skip until it is loaded; the rest run on a small
rem made-up data set.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup.cmd first.
  exit /b 1
)
".venv\Scripts\ruff.exe" format --check src tests scripts || exit /b 1
".venv\Scripts\ruff.exe" check src tests scripts || exit /b 1
".venv\Scripts\mypy.exe" || exit /b 1
rem Every dependency must be free and open source (the owner's licence rule; docs\development.md).
rem pip-licenses prints the whole table on success, so only a failure shows.
".venv\Scripts\pip-licenses.exe" --from=mixed --partial-match --ignore-packages thirteenf --allow-only="MIT;BSD;Apache;ISC;PSF;Python Software Foundation;Mozilla Public License;MPL;Unlicense;0BSD;CC0" >nul || exit /b 1
".venv\Scripts\python.exe" -m pytest -q -rs %* || exit /b 1
rem Every core flow names a unit, integration and UI test, or counts as a gap (docs\core-flows.md).
".venv\Scripts\python.exe" scripts\check_core_flows.py || exit /b 1
rem CLAUDE.md stays at most 600 words; each .claude\rules file is scoped to tracked files and at most 500.
".venv\Scripts\python.exe" scripts\check_claude_files.py
