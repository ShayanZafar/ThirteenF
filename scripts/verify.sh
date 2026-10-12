#!/usr/bin/env sh
# The one check before a change is done. You, Claude and CI all run this.
# Formatting, lint, types, licences, the tests, the core flows map, then the size and scope of Claude's
# instruction files. Tests that need the SEC data skip until it is loaded; the rest run on a small
# made-up data set.
set -e
cd "$(dirname "$0")/.."
BIN=.venv/bin
[ -d .venv/Scripts ] && BIN=.venv/Scripts
if [ ! -d "$BIN" ]; then echo "Run scripts/setup.sh first."; exit 1; fi
"$BIN/ruff" format --check src tests scripts
"$BIN/ruff" check src tests scripts
"$BIN/mypy"
# Every dependency must be free and open source (the owner's licence rule; docs/development.md).
# pip-licenses prints the whole table on success, so only a failure shows.
"$BIN/pip-licenses" --from=mixed --partial-match --ignore-packages thirteenf \
  --allow-only="MIT;BSD;Apache;ISC;PSF;Python Software Foundation;Mozilla Public License;MPL;Unlicense;0BSD;CC0" >/dev/null
"$BIN/python" -m pytest -q -rs "$@"
# Every core flow names a unit, integration and UI test, or counts as a gap (docs/core-flows.md).
"$BIN/python" scripts/check_core_flows.py
# CLAUDE.md stays at most 600 words; each .claude/rules file is scoped to tracked files and at most 500.
"$BIN/python" scripts/check_claude_files.py
