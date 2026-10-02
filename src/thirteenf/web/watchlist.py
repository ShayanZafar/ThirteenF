"""Your watchlist: a CSV of stocks in data/, started from config/watchlist.csv.

It lives outside DuckDB so the web app can change it while the database stays
read-only for every request.
"""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from thirteenf import config

FIELDS = ["ticker", "cusip", "name"]


@dataclass
class Entry:
    cusip: str
    ticker: str = ""
    name: str = ""


def path() -> Path:
    return config.WATCHLIST_PATH


def load() -> list[Entry]:
    """Your watchlist, created from the example list the first time."""
    target = path()
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(config.WATCHLIST_CSV, target)
    with open(target, newline="", encoding="utf-8") as f:
        entries = [
            Entry(cusip=row["cusip"].strip().upper(), ticker=(row.get("ticker") or "").strip().upper(), name=(row.get("name") or "").strip())
            for row in csv.DictReader(f)
            if (row.get("cusip") or "").strip()
        ]
    seen, unique = set(), []
    for entry in entries:
        if entry.cusip not in seen:
            seen.add(entry.cusip)
            unique.append(entry)
    return unique


def save(entries: list[Entry]) -> None:
    """Write through a temporary file, so a crash never leaves half a watchlist."""
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".watchlist-", suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for e in entries:
            writer.writerow({"ticker": e.ticker, "cusip": e.cusip, "name": e.name})
    os.replace(tmp, target)


def cusips() -> set[str]:
    return {e.cusip for e in load()}


def add(cusip: str, ticker: str = "", name: str = "") -> bool:
    """Add a stock. Returns False when it is already on the list."""
    entries = load()
    cusip = cusip.strip().upper()
    if any(e.cusip == cusip for e in entries):
        return False
    entries.append(Entry(cusip=cusip, ticker=ticker.strip().upper(), name=name.strip()))
    save(entries)
    return True


def remove(cusip: str) -> bool:
    entries = load()
    kept = [e for e in entries if e.cusip != cusip.strip().upper()]
    if len(kept) == len(entries):
        return False
    save(kept)
    return True


def replace(old: str, new: str) -> None:
    """Point an entry at a stock's current CUSIP after a change of CUSIP."""
    entries = load()
    if any(e.cusip == new for e in entries):
        kept = [e for e in entries if e.cusip != old]
    else:
        kept = [Entry(cusip=new, ticker=e.ticker, name=e.name) if e.cusip == old else e for e in entries]
    if kept != entries:
        save(kept)
