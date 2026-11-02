"""python -m thirteenf.refresh: the recurring update, meant to run on a schedule.

It runs the whole update (python -m thirteenf.ingest: new 13F data sets, the companies'
financials, tickers, daily prices), which skips what is already here, so a daily run takes
minutes and a run after a new quarter lands takes longer. It holds the update lock, so it
never runs beside another update, and ends by saving the Accumulate list and saying what
entered and left it since the run before, on the command line and in
data/refresh-summary.txt. scripts/schedule-refresh registers it to run every day.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from thirteenf import config, health, runlock
from thirteenf.db import connect
from thirteenf.signals import accumulate


def summary_path():
    return config.DATA_DIR / "refresh-summary.txt"


def _name(r: dict) -> str:
    name = (r.get("name_mixed") or r.get("name_filed") or r["cusip"]).strip()
    ticker = (r.get("ticker") or "").replace("/", ".")
    return f"{ticker} ({name})" if ticker else name


def _quarter(period: date) -> str:
    return f"Q{(period.month - 1) // 3 + 1} {period.year}"


def describe(change: accumulate.RunChange | None, picks: int) -> str:
    """The summary, in plain sentences."""
    if change is None:
        return f"Accumulate list: {picks:,} picks. The next run will say what entered and left."
    lines = [f"Accumulate list for {_quarter(change.period)}: {picks:,} picks."]
    if change.new_period:
        lines.append(
            f"New 13F quarter: the list moved from {_quarter(change.previous_period)} to {_quarter(change.period)}."
        )
    if change.rules_changed:
        lines.append("The list's thresholds changed since the run before, so some moves come from that change.")
    since = (
        f"since the run of {change.previous_at:%b %-d, %Y}"
        if sys.platform != "win32"
        else (f"since the run of {change.previous_at:%b %d, %Y}")
    )
    if not change.entered and not change.left:
        lines.append(f"No change {since}.")
    if change.entered:
        lines.append(f"Entered {since}: " + ", ".join(_name(r) for r in change.entered) + ".")
    if change.left:
        lines.append(f"Left {since}: " + ", ".join(_name(r) for r in change.left) + ".")
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    from thirteenf.ingest import __main__ as ingest

    parser = argparse.ArgumentParser(prog="python -m thirteenf.refresh")
    parser.add_argument("--no-download", action="store_true", help="rebuild from the files already here")
    args = parser.parse_args(argv)
    try:
        with runlock.held("refresh"):
            code = ingest.run(argparse.Namespace(no_download=args.no_download, download_only=False))
            if code:
                print("The update stopped early (see above); nothing new to compare.", file=sys.stderr)
                return code
            with connect() as con:
                change = accumulate.last_change(con)
                picks = accumulate.latest_count(con)
    except runlock.UpdateRunning as err:
        print(err, file=sys.stderr)
        return 3
    text = describe(change, picks)
    warning = health.warning()
    if warning:
        text += f"\nSources: {warning}"
    summary_path().parent.mkdir(parents=True, exist_ok=True)
    summary_path().write_text(text + "\n", encoding="utf-8")
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(run())
