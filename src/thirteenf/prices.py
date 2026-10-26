"""python -m thirteenf.prices fetches daily prices and volume for the stocks that matter.

Which stocks: the market (prices.MARKET), the stocks on your watchlist, and the
Accumulate list's candidates for the period it opens on, with every rule but the
yield and the streak, so the page has prices however you set those two. Stooq is
asked first, Tiingo for what Stooq lacks or once Stooq's daily limit is reached
(docs/sources.md); with no key for either, nothing is fetched and the pages leave
the price columns out. A symbol fetched within the last REFRESH_AFTER is not asked
for again, so a second run the same day picks up where the first stopped. The
model's stock_prices table is rebuilt at the end.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, datetime

from thirteenf import health
from thirteenf.config import ensure_settings_file, stooq_api_key, tiingo_api_key
from thirteenf.db import connect, scalar
from thirteenf.ingest import prices
from thirteenf.ingest.prices import Provider
from thirteenf.model.build import SQL_STOCK_PRICES

ACCUMULATE_MIN_FUNDS = 100


def providers() -> list[Provider]:
    """The sources with a key, primary first."""
    chain: list[Provider] = []
    if stooq_api_key():
        chain.append(prices.Stooq(stooq_api_key()))
    if tiingo_api_key():
        chain.append(prices.Tiingo(tiingo_api_key()))
    return chain


def wanted_symbols(con) -> list[str]:
    """The market, the watchlist's stocks and the Accumulate list's candidates, as symbols."""
    from thirteenf.web import data, watchlist

    symbols = [prices.MARKET]
    if not data.has_cash_flows(con):
        return symbols
    all_periods = data.periods(con)
    period = data.accumulate_period(all_periods).period
    candidates = data.accumulate(con, period, ACCUMULATE_MIN_FUNDS, min_yield=0.0, min_streak=1, limit=10_000)
    tickers = [r["ticker"] for r in candidates if r["ticker"] and r["ticker_source"] != "issuer-name"]
    watched = ", ".join("?" * len(watchlist.cusips())) or "NULL"
    rows = con.execute(
        f"SELECT ticker FROM stocks WHERE cusip IN ({watched}) AND ticker IS NOT NULL AND ticker_source <> 'issuer-name'",
        list(watchlist.cusips()),
    ).fetchall()
    tickers += [r[0] for r in rows]
    symbols += [prices.symbol_key(t) for t in tickers]
    return list(dict.fromkeys(s for s in symbols if s))


def no_key_message() -> str:
    return (
        f"Prices: paste a free Stooq key (stooq.com) into {ensure_settings_file()} to add daily prices and "
        "volume, then run python -m thirteenf.prices"
    )


def update_prices(
    log: Callable[[str], None] = print, chain: list[Provider] | None = None, now: datetime | None = None
) -> dict[str, int] | None:
    """Fetch what is due and rebuild stock_prices. Returns the counts, or None without a key."""
    chain = providers() if chain is None else chain
    if not chain:
        log(no_key_message())
        return None
    now = now or datetime.now(UTC)
    with connect() as con:
        symbols = wanted_symbols(con)
    log(f"Fetching daily prices for {len(symbols):,} symbols ({', then '.join(p.name for p in chain)})")
    try:
        counts = prices.update(connect, chain, symbols, log=log, now=now)
    finally:
        for provider in chain:
            provider.close()
    with connect() as con:
        con.execute(SQL_STOCK_PRICES)
        priced = scalar(con, "SELECT count(DISTINCT cusip) FROM stock_prices")
    left = f", {counts['left']:,} left for the next run" if counts["left"] else ""
    log(
        f"  {counts['fetched']:,} fetched, {counts['no_data']:,} with no data, "
        f"{counts['wanted'] - counts['due']:,} fetched within the last {prices.REFRESH_AFTER.total_seconds() / 3600:.0f} hours{left}; "
        f"{priced:,} stocks have prices"
    )
    return counts


def main() -> int:
    argparse.ArgumentParser(prog="python -m thirteenf.prices").parse_args()
    update_prices()
    warning = health.warning()
    if warning:
        print(f"Sources: {warning} Details in {health.HEALTH_PATH}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
