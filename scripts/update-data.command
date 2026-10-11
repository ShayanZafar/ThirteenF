#!/bin/sh
# macOS: double-click this in Finder to download and load the SEC's 13F data (scripts/update-data.sh,
# in Terminal). About 15 minutes the first time; run it again after each quarter's filings arrive.
cd "$(dirname "$0")" && exec sh ./update-data.sh "$@"
