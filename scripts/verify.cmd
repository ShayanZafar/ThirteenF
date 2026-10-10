@echo off
rem The one check before a change is done. You, Claude and CI all run this.
rem Formatting, lint, types, then the tests. Tests that need the SEC data skip
rem until it is loaded; the rest run on a small made-up data set.
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup.cmd first.
  exit /b 1
)
".venv\Scripts\ruff.exe" format --check src tests || exit /b 1
".venv\Scripts\ruff.exe" check src tests || exit /b 1
".venv\Scripts\mypy.exe" || exit /b 1
".venv\Scripts\python.exe" -m pytest -q -rs %*
