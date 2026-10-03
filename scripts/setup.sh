#!/usr/bin/env sh
# Sets up ThirteenF: a Python 3.12 virtual environment in .venv, the app and its
# dependencies, and data/settings.toml. Safe to run again.
set -e
cd "$(dirname "$0")/.."

PY=""
for candidate in python3.12 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.12 or newer was not found. Install it from https://www.python.org/downloads/"
  exit 1
fi
echo "Python: $PY"

if [ ! -x .venv/bin/python ] && [ ! -x .venv/Scripts/python.exe ]; then
  echo "Creating the virtual environment in .venv ..."
  "$PY" -m venv .venv
fi
VENV_PY=.venv/bin/python
[ -x .venv/Scripts/python.exe ] && VENV_PY=.venv/Scripts/python.exe

echo "Installing ThirteenF and its dependencies ..."
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -e ".[dev]"
"$VENV_PY" -c "from thirteenf.config import ensure_settings_file; print('Settings file:', ensure_settings_file())"

if ! "$VENV_PY" -c "import sys; from thirteenf.config import user_setting; sys.exit(0 if user_setting('SEC_USER_AGENT') else 1)"; then
  echo
  echo "SEC_USER_AGENT is not set. The SEC asks every client for a name and contact email."
  echo "Add this to your shell profile (~/.zshrc or ~/.bashrc), then open a new terminal:"
  echo '    export SEC_USER_AGENT="ThirteenF you@example.com"'
fi
echo
echo "Setup done. Next:"
echo "  scripts/update-data.sh   download and load the SEC's 13F data (about 15 minutes the first time)"
echo "  scripts/start.sh         open the app at http://127.0.0.1:8000"
