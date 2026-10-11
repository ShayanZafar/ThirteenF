#!/bin/sh
# macOS: double-click this in Finder to start ThirteenF. It opens Terminal and runs scripts/start.sh,
# which sets the app up the first time and opens it in your browser.
cd "$(dirname "$0")" && exec sh ./start.sh "$@"
