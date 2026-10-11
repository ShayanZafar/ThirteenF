#!/usr/bin/env sh
# Starts ThirteenF at http://127.0.0.1:8000 and opens it in your browser. The first time, it runs
# scripts/setup.sh for you (Python 3.12 or newer must be installed). On macOS, double-click
# scripts/start.command instead; it runs this.
# Options: --port 8001 to use another port, --reload while changing the code.
set -e
cd "$(dirname "$0")/.."
# The virtual environment's Python: .venv/bin on macOS and Linux, .venv/Scripts in Git Bash on Windows.
venv_python() {
  if [ -x .venv/Scripts/python.exe ]; then echo .venv/Scripts/python.exe; else echo .venv/bin/python; fi
}
if [ ! -x "$(venv_python)" ]; then
  echo "First run: setting ThirteenF up (a minute or two) ..."
  echo
  sh scripts/setup.sh
  echo
fi
[ -f data/thirteenf.duckdb ] || echo "There is no data yet: run scripts/update-data.sh first. The app will say so too."
exec "$(venv_python)" -m thirteenf.web --open "$@"
