"""Read-only queries on the model tables for the web pages."""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date

import duckdb

from thirteenf.config import DB_PATH
from thirteenf.db import Busy, connect  # noqa: F401  (Busy is raised from here)
from thirteenf.web.format import display_name, ticker as ticker_text


class NoData(RuntimeError):
    pass


@contextmanager
def connection():
    """One read-only connection per request, so ingest can write between requests.
    Raises Busy when a writer holds the database for more than a moment."""
    if not DB_PATH.exists():
        raise NoData()
    con = connect(read_only=True, wait_seconds=3)
    try:
        tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        if "stock_periods" not in tables:
            raise NoData()
        yield con
    finally:
        con.close()


def _rows(con, sql: str, params=None) -> list[dict]:
    cursor = con.execute(sql, params or [])
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


@dataclass
class Period:
    period: date
    label: str
    prev_period: date | None
    deadline: date
    complete: bool
    data_through: date
    filers: int
    filers_pct: float | None
    market_median_pct: float | None
    market_median_stocks: int | None


def periods(con) -> list[Period]:
    rows = _rows(
        con,
        """
        SELECT p.period, p.label, p.prev_period, p.deadline, p.complete, p.data_through, ft.filers,
               ft.filers::DOUBLE / NULLIF(prev.filers, 0) - 1 AS filers_pct,
               m.market_median_pct, m.market_median_stocks
        FROM periods p
        JOIN filers_total ft USING (period)
        LEFT JOIN filers_total prev ON prev.period = p.prev_period
        LEFT JOIN (SELECT DISTINCT period, market_median_pct, market_median_stocks FROM stock_periods
                   WHERE market_median_pct IS NOT NULL) m USING (period)
        ORDER BY p.period
        """,
    )
    return [Period(**r) for r in rows]


@dataclass
class Security:
    cusip: str
    stock: str  # the stock's current CUSIP; differs when this CUSIP was replaced
    name: str
    name_filed: str
    title_of_class: str | None
    figi: str | None
    latest_period: date
    ticker: str = ""  # from OpenFIGI, as people write it (BRK.B)
    security_type: str | None = None  # OpenFIGI's: Common Stock, ETP, ADR, ...
    kind: str = "stock"  # stock, etf or other


def security(con, cusip: str) -> Security | None:
    """A CUSIP, named the way its stock is named."""
    rows = _rows(
        con,
        """
        SELECT s.cusip, s.stock, s.latest_period,
               coalesce(st.name_filed, s.name_filed) AS name_filed,
               coalesce(st.name_mixed, s.name_mixed) AS name_mixed,
               coalesce(st.title_of_class, s.title_of_class) AS title_of_class,
               coalesce(st.figi, s.figi) AS figi,
               st.ticker, st.security_type, st.kind
        FROM securities s
        LEFT JOIN stocks st ON st.cusip = s.stock
        WHERE s.cusip = ?
        """,
        [cusip.upper()],
    )
    if not rows:
        return None
    r = rows[0]
    return Security(
        cusip=r["cusip"],
        stock=r["stock"],
        name=display_name(r["name_filed"], r["name_mixed"]),
        name_filed=r["name_filed"],
        title_of_class=r["title_of_class"],
        figi=r["figi"],
        latest_period=r["latest_period"],
        ticker=ticker_text(r["ticker"]),
        security_type=r["security_type"],
        kind=r["kind"] or "stock",
    )


def earlier_cusips(con, stock: str) -> list[dict]:
    """The CUSIP changes that led to this stock's current CUSIP, oldest first."""
    rows = _rows(
        con,
        """
        SELECT c.period, p.label, c.old_cusip, c.new_cusip, c.exchange_ratio, c.moved, c.departed,
               s.name_filed, s.name_mixed
        FROM cusip_changes c
        JOIN stock_keys k ON k.cusip = c.old_cusip
        JOIN periods p ON p.period = c.period
        LEFT JOIN securities s ON s.cusip = c.old_cusip
        WHERE k.stock = ?
        ORDER BY c.period, c.old_cusip
        """,
        [stock.upper()],
    )
    for r in rows:
        r["name"] = display_name(r["name_filed"], r["name_mixed"])
    return rows


@dataclass
class StockPeriod:
    period: date
    label: str
    held: bool  # any 13F filer reported shares this period
    funds: int
    funds_prev: int | None
    funds_change: int | None
    funds_pct: float | None
    filers: int
    filers_pct: float | None
    share_of_filers: float | None
    market_median_pct: float | None
    vs_tide_pts: float | None
    vs_median_pts: float | None
    shares: int | None
    shares_prev: int | None
    shares_pct: float | None
    value: int | None
    value_pct: float | None
    price_pct: float | None
    share_check: str  # ok, none, outran
    shares_vs_value_pts: float | None
    flagged_rows: int
    thousands_rows: int
    median_price: float | None
    streak: int
    direction: int | None
    prev_period: date | None = None

    @property
    def shares_shown(self) -> bool:
        return self.held and self.shares is not None and self.share_check != "outran"

    @property
    def shares_change_shown(self) -> bool:
        return self.shares_shown and self.share_check == "ok" and self.shares_prev is not None

    @property
    def shares_change(self) -> int | None:
        if not self.shares_change_shown:
            return None
        return self.shares - self.shares_prev


def stock_series(con, cusip: str, all_periods: list[Period]) -> list[StockPeriod]:
    """The stock's current run of held periods, oldest first, through the latest period.

    The run starts after the last period in which no filer reported the stock, so a
    single filer reporting a private company years before it listed does not open
    the history. Periods after the run, when no filer reports it any more (after an
    acquisition, say), count as zero funds."""
    rows = {
        r["period"]: r
        for r in _rows(
            con,
            """
            SELECT sp.*, h.thousands_rows
            FROM stock_periods sp JOIN holders h USING (cusip, period)
            WHERE sp.cusip = ? ORDER BY sp.period
            """,
            [cusip.upper()],
        )
    }
    if not rows:
        return []
    order = [p.period for p in all_periods]
    start = order.index(max(rows))
    while start > 0 and order[start - 1] in rows:
        start -= 1
    series: list[StockPeriod] = []
    for p in all_periods[start:]:
        r = rows.get(p.period)
        prev = series[-1] if series else None
        if r is None:
            funds_prev = prev.funds if prev else None
            series.append(
                StockPeriod(
                    period=p.period, label=p.label, held=False, funds=0, funds_prev=funds_prev,
                    funds_change=(-funds_prev if funds_prev else None),
                    funds_pct=(-1.0 if funds_prev else None),
                    filers=p.filers, filers_pct=p.filers_pct, share_of_filers=0.0,
                    market_median_pct=p.market_median_pct,
                    vs_tide_pts=((-1.0 - p.filers_pct) * 100 if funds_prev and p.filers_pct is not None else None),
                    vs_median_pts=((-1.0 - p.market_median_pct) * 100 if funds_prev and p.market_median_pct is not None else None),
                    shares=None, shares_prev=None, shares_pct=None, value=None, value_pct=None, price_pct=None,
                    share_check="none", shares_vs_value_pts=None, flagged_rows=0, thousands_rows=0,
                    median_price=None, streak=0, direction=(-1 if funds_prev else None),
                    prev_period=p.prev_period,
                )
            )
            continue
        funds_prev = r["funds_prev"] if prev is not None else None
        series.append(
            StockPeriod(
                period=p.period, label=p.label, held=True, funds=r["funds_holding"], funds_prev=funds_prev,
                funds_change=(r["funds_holding"] - funds_prev if funds_prev is not None else None),
                funds_pct=r["funds_pct"], filers=r["filers"], filers_pct=r["filers_pct"],
                share_of_filers=r["share_of_filers"], market_median_pct=r["market_median_pct"] if r["market_median_pct"] is not None else p.market_median_pct,
                vs_tide_pts=r["vs_tide_pts"], vs_median_pts=r["vs_median_pts"],
                shares=r["shares"], shares_prev=r["shares_prev"], shares_pct=r["shares_pct"],
                value=r["value"], value_pct=r["value_pct"], price_pct=r["price_pct"],
                share_check=r["share_check"], shares_vs_value_pts=r["shares_vs_value_pts"],
                flagged_rows=r["flagged_rows"], thousands_rows=r["thousands_rows"],
                median_price=r["median_price"], streak=r["streak"],
                direction=(int(r["direction"]) if r["direction"] is not None else None),
                prev_period=p.prev_period,
            )
        )
    _restreak(series)
    return series


def _restreak(series: list[StockPeriod]) -> None:
    """Streaks across the filled-in series: consecutive periods with the same direction."""
    run = 0
    last = None
    for row in series:
        d = None if row.funds_change is None else (row.funds_change > 0) - (row.funds_change < 0)
        row.direction = d
        if d is None or d == 0:
            run = 0
        elif d == last:
            run += 1
        else:
            run = 1
        last = d
        row.streak = run


def left_out_rows(con, stock: str, period: date, limit: int = 10) -> tuple[list[dict], int]:
    """Reports left out of the share total, across every CUSIP of the stock."""
    rows = _rows(
        con,
        """
        SELECT manager_name, cik, cusip, shares, value, implied_price, median_price, price_ratio, reason
        FROM price_check
        WHERE cusip IN (SELECT cusip FROM stock_keys WHERE stock = ?) AND period = ? AND left_out
        ORDER BY shares DESC
        """,
        [stock.upper(), period],
    )
    return rows[:limit], len(rows)


CUSIP = re.compile(r"\b([0-9A-Za-z]{8}[0-9])\b")
TICKER_KEY = "regexp_replace(upper(coalesce(cur.ticker, '')), '[^A-Z0-9]', '', 'g')"
SUFFIXES = {
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED",
    "PLC", "LLC", "LP", "SA", "NV", "AG", "SE", "THE", "COM", "CL", "CLASS", "A",
}


CLASS_HINT = re.compile(r"\b(?:class|cl)\.?\s+([a-z])\b", re.I)
# Whether a stock's class or name says that share class: CL A, CLASS A.
CLASS_MATCH = (
    r"(? <> '' AND regexp_matches(upper(coalesce(cur.title_of_class, '') || ' ' || cur.name_filed),"
    r" '\bCL(ASS)?\s*' || ? || '\b'))"
)


def compact_key(text: str) -> str:
    """Letters and digits only, upper case: 'brk.b' and 'BRK/B' both give BRKB."""
    return re.sub(r"[^0-9A-Z]", "", (text or "").upper())


def name_key(text: str) -> str:
    """A company name without the words that differ between filers: 'Apple' = 'APPLE INC'."""
    words = [w for w in re.split(r"[^0-9A-Z&]+", (text or "").upper()) if w and w not in SUFFIXES]
    return "".join(words)


def search(con, query: str, limit: int = 25) -> list[dict]:
    """Stocks matching a ticker, a CUSIP or every word of a name, best match first:
    an exact ticker, then the most widely held."""
    query = query.strip()
    if not query:
        return []
    latest = con.execute("SELECT max(period) FROM periods").fetchone()[0]
    key = compact_key(query)
    match = CUSIP.search(query)
    params: list = []
    share_class = ""
    if match and any(ch.isdigit() for ch in match.group(1)[:8]):
        where = "s.cusip = ?"
        params.append(match.group(1).upper())
    else:
        # "class A" or "cl A" ranks that share class first instead of having to match.
        hint = CLASS_HINT.search(query)
        if hint:
            share_class = hint.group(1).upper()
            query = CLASS_HINT.sub(" ", query)
        words = [w for w in re.split(r"[^0-9A-Za-z&]+", query) if w]
        if not words:
            return []
        # Every word in the name or the share class ("Berkshire Hathaway class B").
        where = " AND ".join(
            [
                "(s.name_filed ILIKE ? OR coalesce(s.name_mixed, '') ILIKE ? OR s.cusip ILIKE ?"
                " OR coalesce(s.title_of_class, '') ILIKE ?)"
            ]
            * len(words)
        )
        for w in words:
            params += [f"%{w}%", f"%{w}%", f"{w}%", f"%{w}%"]
    # Match any CUSIP a stock was reported under, or its ticker; list each stock
    # once, by its current CUSIP.
    rows = _rows(
        con,
        f"""
        WITH matched AS (
            SELECT DISTINCT s.stock FROM securities s WHERE {where}
            UNION
            SELECT cur.cusip FROM stocks cur
            WHERE length(?) BETWEEN 1 AND 6 AND starts_with({TICKER_KEY}, ?)
        )
        SELECT cur.cusip, cur.ticker, cur.security_type, cur.kind, cur.name_filed, cur.name_mixed, cur.title_of_class,
               coalesce(h.funds_holding, 0) AS funds,
               {TICKER_KEY} = ? AND ? <> '' AS ticker_match,
               {CLASS_MATCH} AS class_match
        FROM matched m
        JOIN stocks cur ON cur.cusip = m.stock
        LEFT JOIN holders h ON h.cusip = m.stock AND h.period = ?
        ORDER BY ticker_match DESC, class_match DESC, funds DESC, cur.name_filed
        LIMIT {int(limit)}
        """,
        params + [key, key, key, key, share_class, share_class, latest],
    )
    for r in rows:
        r["name"] = display_name(r["name_filed"], r["name_mixed"])
        r["ticker"] = ticker_text(r["ticker"])
    return rows


def best_match(results: list[dict], query: str) -> dict | None:
    """The one stock a query clearly means: its ticker, its CUSIP, its name, or the only match."""
    query = query.strip()
    if not results:
        return None
    exact = [r for r in results if r["cusip"] == query.upper() or r.get("ticker_match")]
    if len(exact) == 1:
        return exact[0]
    if len(results) == 1:
        return results[0]
    named = [r for r in results if name_key(r["name"]) == name_key(query) and name_key(query)]
    if len(named) == 1:
        return named[0]
    return None


RANKINGS = {
    "tide": "vs_tide_pts",  # change in funds holding against the change in all 13F filers
    "count": "funds_change",  # change in the number of funds
}


# The tabs on the Biggest changes page: which kinds each one shows.
KINDS = {"all": None, "stocks": "stock", "etfs": "etf"}


def _kind_rule(kind: str) -> tuple[str, list]:
    """A WHERE fragment (on stocks s) and its parameters for a tab."""
    wanted = KINDS[kind]
    return ("AND s.kind = ?", [wanted]) if wanted else ("", [])


def ranked_changes(
    con, period: date, minimum: int, by: str, limit: int, most: str, kind: str = "all"
) -> list[dict]:
    """Stocks held by at least `minimum` funds in both periods, ranked by their change.

    most="added" ranks from the top, most="lost" from the bottom. kind is a tab:
    all, stocks or etfs."""
    column = RANKINGS[by]
    direction = "DESC" if most == "added" else "ASC"
    kind_rule, kind_params = _kind_rule(kind)
    rows = _rows(
        con,
        f"""
        SELECT sp.cusip, s.name_filed, s.name_mixed, s.title_of_class, s.ticker, s.security_type, s.kind,
               sp.funds_holding AS funds, sp.funds_prev, sp.funds_change, sp.funds_pct,
               sp.filers_pct, sp.vs_tide_pts, sp.market_median_pct, sp.vs_median_pts,
               sp.shares, sp.shares_prev, sp.shares_pct, sp.share_check, sp.streak, sp.direction
        FROM stock_periods sp
        JOIN stocks s ON s.cusip = sp.cusip
        WHERE sp.period = ? AND sp.funds_holding >= ? AND sp.funds_prev >= ?
          AND sp.{column} {">" if most == "added" else "<"} 0 {kind_rule}
        ORDER BY sp.{column} {direction}, sp.cusip
        LIMIT ?
        """,
        [period, minimum, minimum, *kind_params, limit],
    )
    for r in rows:
        r["name"] = display_name(r["name_filed"], r["name_mixed"])
        r["ticker"] = ticker_text(r["ticker"])
    return rows


def change_summary(con, period: date, minimum: int, kind: str = "all") -> dict:
    """How the stocks compared moved in a period, for the page's key figures."""
    kind_rule, kind_params = _kind_rule(kind)
    summary = _rows(
        con,
        f"""
        SELECT count(*) AS stocks,
               count(*) FILTER (WHERE sp.funds_change > 0) AS more,
               count(*) FILTER (WHERE sp.funds_change < 0) AS fewer,
               median(sp.funds_pct) AS median_pct
        FROM stock_periods sp
        JOIN stocks s ON s.cusip = sp.cusip
        WHERE sp.period = ? AND sp.funds_holding >= ? AND sp.funds_prev >= ? {kind_rule}
        """,
        [period, minimum, minimum, *kind_params],
    )[0]
    tide = _rows(
        con,
        """
        SELECT ft.filers, ft.filers::DOUBLE / NULLIF(prev.filers, 0) - 1 AS filers_pct
        FROM filers_total ft
        JOIN periods p USING (period)
        LEFT JOIN filers_total prev ON prev.period = p.prev_period
        WHERE ft.period = ?
        """,
        [period],
    )[0]
    return {**summary, **tide}


def kind_counts(con, period: date, minimum: int) -> dict[str, int]:
    """How many stocks each tab compares."""
    counts = dict(
        con.execute(
            """
            SELECT s.kind, count(*)
            FROM stock_periods sp JOIN stocks s ON s.cusip = sp.cusip
            WHERE sp.period = ? AND sp.funds_holding >= ? AND sp.funds_prev >= ?
            GROUP BY 1
            """,
            [period, minimum, minimum],
        ).fetchall()
    )
    return {"all": sum(counts.values()), "stocks": counts.get("stock", 0), "etfs": counts.get("etf", 0)}
