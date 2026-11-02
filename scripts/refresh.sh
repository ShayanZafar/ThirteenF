#!/usr/bin/env sh
# The recurring update: runs update-data (which skips what is already here), then says what
# entered and left the Accumulate list since the run before, here and in data/refresh-summary.txt.
# It never runs beside another update. To run it every day at 07:00 on macOS or Linux, add this
# line with `crontab -e` (with your own path and SEC_USER_AGENT):
#   0 7 * * * SEC_USER_AGENT="ThirteenF you@example.com" /path/to/ThirteenF/scripts/refresh.sh
set -e
cd "$(dirname "$0")/.."
if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; else PY=.venv/bin/python; fi
if [ ! -x "$PY" ]; then echo "Run scripts/setup.sh first."; exit 1; fi
exec "$PY" -m thirteenf.refresh "$@"
