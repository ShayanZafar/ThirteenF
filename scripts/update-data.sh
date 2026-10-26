#!/usr/bin/env sh
# Downloads any new SEC Form 13F data sets, loads them, rebuilds the model and, with keys in
# data/settings.toml, maps new CUSIPs to tickers (OpenFIGI) and fetches daily prices (Stooq). The first time, it runs scripts/setup.sh
# for you. On macOS, double-click scripts/update-data.command instead; it runs this.
# Pass --no-download to rebuild from the zips already in data/raw.
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
echo "Updating the 13F data. The first run downloads about 800 MB and takes about 15 minutes;"
echo "later runs only fetch new quarters. If the app is open, its pages say the data is being updated until this finishes."
echo
"$(venv_python)" -m thirteenf.ingest "$@"
echo
echo "Done. The app shows the new data; start it with scripts/start.sh if it isn't open."
