#!/usr/bin/env sh
# Downloads any new SEC Form 13F data sets, loads them, rebuilds the model and,
# with an OpenFIGI key in data/settings.toml, maps new CUSIPs to tickers.
# Pass --no-download to rebuild from the zips already in data/raw.
set -e
cd "$(dirname "$0")/.."
# The virtual environment's Python: .venv/bin on macOS and Linux, .venv/Scripts in Git Bash on Windows.
VENV_PY=.venv/bin/python
[ -x .venv/Scripts/python.exe ] && VENV_PY=.venv/Scripts/python.exe
if [ ! -x "$VENV_PY" ]; then echo "Run scripts/setup.sh first."; exit 1; fi
echo "Updating the 13F data. The first run downloads about 800 MB and takes about 15 minutes;"
echo "later runs only fetch new quarters. If the app is open, its pages say the data is being updated until this finishes."
echo
exec "$VENV_PY" -m thirteenf.ingest "$@"
