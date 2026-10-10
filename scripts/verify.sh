#!/usr/bin/env sh
# The one check before a change is done. You, Claude and CI all run this.
# Formatting, lint, types, then the tests. Tests that need the SEC data skip
# until it is loaded; the rest run on a small made-up data set.
set -e
cd "$(dirname "$0")/.."
BIN=.venv/bin
[ -d .venv/Scripts ] && BIN=.venv/Scripts
if [ ! -d "$BIN" ]; then echo "Run scripts/setup.sh first."; exit 1; fi
"$BIN/ruff" format --check src tests
"$BIN/ruff" check src tests
"$BIN/mypy"
"$BIN/python" -m pytest -q -rs "$@"
