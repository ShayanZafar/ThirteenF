#!/usr/bin/env sh
# Runs one ThirteenF command with the app's own Python in .venv, never another Python on PATH.
#   scripts/run.sh tickers --retry-missing
#   scripts/run.sh prices
# Commands: ingest, refresh, model, prices, tickers, web. With none, it lists them.
set -e
cd "$(dirname "$0")/.."
# The virtual environment's Python: .venv/bin on macOS and Linux, .venv/Scripts in Git Bash on Windows.
VENV_PY=.venv/bin/python
[ -x .venv/Scripts/python.exe ] && VENV_PY=.venv/Scripts/python.exe
if [ ! -x "$VENV_PY" ]; then echo "Run scripts/setup.sh first."; exit 1; fi
exec "$VENV_PY" -m thirteenf "$@"
