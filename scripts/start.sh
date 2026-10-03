#!/usr/bin/env sh
# Starts ThirteenF at http://127.0.0.1:8000 and opens it in your browser.
# Options: --port 8001 to use another port, --reload while changing the code.
set -e
cd "$(dirname "$0")/.."
# The virtual environment's Python: .venv/bin on macOS and Linux, .venv/Scripts in Git Bash on Windows.
VENV_PY=.venv/bin/python
[ -x .venv/Scripts/python.exe ] && VENV_PY=.venv/Scripts/python.exe
if [ ! -x "$VENV_PY" ]; then echo "Run scripts/setup.sh first."; exit 1; fi
[ -f data/thirteenf.duckdb ] || echo "There is no data yet: run scripts/update-data.sh first. The app will say so too."
exec "$VENV_PY" -m thirteenf.web --open "$@"
