"""The model tables the list pages read, written by hand into an in-memory DuckDB.

For unit tests of one query in thirteenf.web.data: each row states only what the test
is about, and the rest takes a plain default. The derived columns follow the definitions
in docs/13f-data.md (the change in funds, and the change against the tide in points), so a
test sets funds and the tide and reads the ranking, as a person would.
"""

from __future__ import annotations

from datetime import date

import duckdb

STOCKS = {
    "cusip": "VARCHAR",
    "name_filed": "VARCHAR",
    "name_mixed": "VARCHAR",
    "title_of_class": "VARCHAR",
    "ticker": "VARCHAR",
    "security_type": "VARCHAR",
    "kind": "VARCHAR",
    "ticker_source": "VARCHAR",
    "ticker_as_of": "DATE",
}
STOCK_PERIODS = {
    "cusip": "VARCHAR",
    "period": "DATE",
    "funds_holding": "INTEGER",
    "funds_prev": "INTEGER",
    "funds_change": "INTEGER",
    "funds_pct": "DOUBLE",
    "filers_pct": "DOUBLE",
    "vs_tide_pts": "DOUBLE",
    "market_median_pct": "DOUBLE",
    "vs_median_pts": "DOUBLE",
    "shares": "DOUBLE",
    "shares_prev": "DOUBLE",
    "shares_pct": "DOUBLE",
    "share_check": "VARCHAR",
    "streak": "INTEGER",
    "direction": "INTEGER",
    "net_flow": "DOUBLE",
    "price_pct": "DOUBLE",
    "median_price": "DOUBLE",
    "value": "DOUBLE",
}
STOCK_CASH_FLOWS = {
    "cusip": "VARCHAR",
    "free_cash_flow": "DOUBLE",
    "prior_free_cash_flow": "DOUBLE",
    "lower_free_cash_flow": "DOUBLE",
    "fiscal_end": "DATE",
    "prior_fiscal_end": "DATE",
    "entity_name": "VARCHAR",
    "diluted_shares": "DOUBLE",
    "shares_outstanding": "DOUBLE",
    "financial": "BOOLEAN",
}

STOCK_PRICES = {
    "cusip": "VARCHAR",
    "period": "DATE",
    "start_close": "DOUBLE",
    "end_close": "DOUBLE",
    "latest_close": "DOUBLE",
    "latest_day": "DATE",
    "since_start_pct": "DOUBLE",
    "quarter_pct": "DOUBLE",
    "dollar_volume": "DOUBLE",
    "days_traded": "INTEGER",
    "market_since_start_pct": "DOUBLE",
    "vs_market_pts": "DOUBLE",
    "price_source": "VARCHAR",
}

PERIOD = date(2024, 12, 31)


def stock(cusip: str, name: str, kind: str = "stock", **overrides) -> dict:
    return {"cusip": cusip, "name_filed": name.upper(), "name_mixed": name, "kind": kind, **overrides}


def stock_period(cusip: str, funds: int, funds_prev: int, filers_pct: float = 0.0, **overrides) -> dict:
    """A stock's period: funds holding now and before, against all 13F filers' change."""
    funds_pct = funds / funds_prev - 1
    change = funds - funds_prev
    row = {
        "cusip": cusip,
        "period": PERIOD,
        "funds_holding": funds,
        "funds_prev": funds_prev,
        "funds_change": change,
        "funds_pct": funds_pct,
        "filers_pct": filers_pct,
        "vs_tide_pts": (funds_pct - filers_pct) * 100,
        "share_check": "ok",
        "streak": 1,
        "direction": (change > 0) - (change < 0),
        "net_flow": 0.0,
        "median_price": 100.0,
        "value": 0.0,
    }
    return row | overrides


def cash_flow(cusip: str, free_cash_flow: float, prior: float, diluted_shares: float, **overrides) -> dict:
    """A company's last two fiscal years of free cash flow, to Sep 30, 2024 and the year before."""
    row = {
        "cusip": cusip,
        "free_cash_flow": free_cash_flow,
        "prior_free_cash_flow": prior,
        "lower_free_cash_flow": min(free_cash_flow, prior),
        "fiscal_end": date(2024, 9, 30),
        "prior_fiscal_end": date(2023, 9, 30),
        "entity_name": cusip,
        "diluted_shares": diluted_shares,
        "shares_outstanding": diluted_shares,
        "financial": False,
    }
    return row | overrides


def _table(con: duckdb.DuckDBPyConnection, name: str, columns: dict[str, str], rows: list[dict]) -> None:
    con.execute(f"CREATE TABLE {name} ({', '.join(f'{c} {t}' for c, t in columns.items())})")
    for row in rows:
        unknown = set(row) - set(columns)
        assert not unknown, f"{name} has no columns {unknown}"
        con.execute(
            f"INSERT INTO {name} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
            list(row.values()),
        )


def prices(cusip: str, since_start_pct: float, market_pct: float = 0.0, **overrides) -> dict:
    """A stock's price since the quarter's start (Sep 30, 2024) to Jan 15, 2025, against the market's."""
    row = {
        "cusip": cusip,
        "period": PERIOD,
        "start_close": 100.0,
        "end_close": 100.0 * (1 + since_start_pct),
        "latest_close": 100.0 * (1 + since_start_pct),
        "latest_day": date(2025, 1, 15),
        "since_start_pct": since_start_pct,
        "quarter_pct": since_start_pct,
        "dollar_volume": 1e9,
        "days_traded": 63,
        "market_since_start_pct": market_pct,
        "vs_market_pts": (since_start_pct - market_pct) * 100,
        "price_source": "stooq",
    }
    return row | overrides


def model(
    stocks: list[dict],
    stock_periods: list[dict],
    cash_flows: list[dict] | None = None,
    stock_prices: list[dict] | None = None,
):
    """An in-memory database holding just these rows."""
    con = duckdb.connect()
    _table(con, "stocks", STOCKS, stocks)
    _table(con, "stock_periods", STOCK_PERIODS, stock_periods)
    if cash_flows is not None:
        _table(con, "stock_cash_flows", STOCK_CASH_FLOWS, cash_flows)
    if stock_prices is not None:
        _table(con, "stock_prices", STOCK_PRICES, stock_prices)
    return con
