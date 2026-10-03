#!/usr/bin/env sh
# Runs the tests. Tests that need the SEC data skip until it is loaded.
# Pass pytest options through, for example: scripts/test.sh -k tickers
set -e
cd "$(dirname "$0")/.."
# The virtual environment's Python: .venv/bin on macOS and Linux, .venv/Scripts in Git Bash on Windows.
VENV_PY=.venv/bin/python
[ -x .venv/Scripts/python.exe ] && VENV_PY=.venv/Scripts/python.exe
if [ ! -x "$VENV_PY" ]; then echo "Run scripts/setup.sh first."; exit 1; fi
exec "$VENV_PY" -m pytest "$@"
