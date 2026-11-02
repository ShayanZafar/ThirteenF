"""Read helpers shared by the pages, the commands and the signals: rows as dicts, and
checks for tables and columns a database built by an older version may not have yet."""

from __future__ import annotations

from thirteenf.db import scalar


def rows(con, sql: str, params=None) -> list[dict]:
    cursor = con.execute(sql, params or [])
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def ticker_source_columns(con, alias: str = "st") -> str:
    """The stock's ticker source and date (from the stocks table as `alias`), or NULLs
    in a database built before tickers had fallbacks."""
    present = scalar(
        con,
        "SELECT count(*) FROM information_schema.columns WHERE table_name = 'stocks' AND column_name = 'ticker_source'",
    )
    return f"{alias}.ticker_source, {alias}.ticker_as_of" if present else "NULL AS ticker_source, NULL AS ticker_as_of"


def has_table(con, name: str) -> bool:
    return bool(scalar(con, "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]))


def has_prices(con) -> bool:
    """Whether the model has daily prices: the table exists and holds a row."""
    return has_table(con, "stock_prices") and bool(scalar(con, "SELECT count(*) FROM stock_prices"))


def has_cash_flows(con) -> bool:
    """Whether the model has the companies' financials: a database built before
    they were added has no stock_cash_flows table until update-data runs."""
    return has_table(con, "stock_cash_flows")
