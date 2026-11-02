"""The Accumulate list's rule: stocks funds keep moving into, against the tide, whose
free cash flow is high for their market value (docs/13f-data.md, "Accumulate list").

One place for the rule, its thresholds and the period it opens on, so the page, the
price command (which prices the candidates) and the recurring refresh all agree. The
picks come back as the model holds them; the pages name them (thirteenf.web.data).
Each update saves the list it ends with in accumulate_runs, so a later run can say
what entered and left.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from thirteenf.db import scalar
from thirteenf.model.read import has_cash_flows, has_prices, has_table, rows, ticker_source_columns


class PeriodLike(Protocol):
    period: date
    prev_period: date | None
    deadline: date
    data_through: date


MIN_FUNDS = 100  # funds holding at both dates, the default the page opens with

# Stocks funds keep moving into, whose free cash flow is
# high for their market value. See docs/13f-data.md, "Accumulate list".
RANKINGS = {"yield": "fcf_yield DESC", "tide": "vs_tide_pts DESC", "price": "vs_market_pts ASC NULLS LAST"}
# How far a pick's price may have moved against the market since the quarter funds bought
# in, in points, and still count as lagging (not priced in yet) or ahead.
PRICE_LAG_PTS = 5.0
MIN_YIELD = 0.05  # free cash flow at least 5% of market value
MIN_STREAK = 2  # more funds two periods running, or longer
# Market value is the 13F price times the diluted share count, so two checks
# guard the share count, each within this factor: it must agree with the latest
# cover-page count (a split since the fiscal year end moves one and not the
# other), and funds' 13F holdings must not be worth more than the whole company.
SHARES_AGREE = 1.5
# Financials older than this, counted from the period, are too stale to compare.
FISCAL_MAX_AGE_MONTHS = 18


def choose_period[P: PeriodLike](all_periods: list[P]) -> P:
    """The latest period whose on-time filings are all in, else the latest one."""
    choices = [p for p in all_periods if p.prev_period is not None]
    on_time = [p for p in choices if p.deadline <= p.data_through]
    return (on_time or choices)[-1]


# The SEC publishes a three-month data set some days after the window ends, and a period's
# filing deadline falls in the window's last month, so a period's list could first be read
# about this long after the end of its deadline's month. An assumption, stated on the backtest
# page: the SEC gives no publication date.
PUBLISH_LAG_DAYS = 14


def list_date(deadline: date) -> date:
    """The first day a period's list could be read: PUBLISH_LAG_DAYS after the end of the
    month its filing deadline falls in (the end of its data set's window)."""
    next_month = date(deadline.year + deadline.month // 12, deadline.month % 12 + 1, 1)
    return next_month - timedelta(days=1) + timedelta(days=PUBLISH_LAG_DAYS)


def _from(con, known_by: date | None) -> str:
    """The tables the rule reads. With known_by, each company's financials are the latest
    fiscal year known by that day (fundamentals_history.known_from), as a person reading
    the list then would have had them; without it, the latest there are."""
    cash_flows = "stock_cash_flows"
    if known_by is not None and has_table(con, "stock_cash_flows_history"):
        cash_flows = f"""(SELECT DISTINCT ON (cusip) * FROM stock_cash_flows_history
                 WHERE known_from <= DATE '{known_by.isoformat()}' ORDER BY cusip, fiscal_end DESC)"""
    return f"""
    FROM stock_periods sp
    JOIN stocks s ON s.cusip = sp.cusip
    JOIN {cash_flows} cf ON cf.cusip = sp.cusip
"""


_WHERE = f"""sp.period = ? AND sp.funds_holding >= ? AND sp.funds_prev >= ?
      AND cf.fiscal_end > sp.period - INTERVAL {FISCAL_MAX_AGE_MONTHS} MONTH"""
_COMPARABLE = "cf.prior_free_cash_flow IS NOT NULL AND NOT cf.financial AND sp.median_price > 0"
_SHARES_AGREE = (
    f"(cf.shares_outstanding IS NULL OR cf.shares_outstanding / cf.diluted_shares BETWEEN {1 / SHARES_AGREE} AND {SHARES_AGREE})"
    f" AND sp.value <= {SHARES_AGREE} * sp.median_price * cf.diluted_shares"
)


def picks(
    con,
    period: date,
    minimum: int,
    min_yield: float,
    min_streak: int,
    by: str = "yield",
    limit: int = 50,
    known_by: date | None = None,
) -> list[dict]:
    """Stocks with more funds against the tide for `min_streak` periods running, a
    positive net 13F flow, positive free cash flow in each of their last two fiscal
    years, and the lower of the two at least `min_yield` of market value. With known_by,
    only financials known by that day count (_from)."""
    order = RANKINGS[by]
    price_columns, price_join = _price_join(con)
    found = rows(
        con,
        f"""
        SELECT * FROM (
            SELECT sp.cusip, s.name_filed, s.name_mixed, s.title_of_class, s.ticker,
                   {ticker_source_columns(con, "s")}, {price_columns},
                   sp.funds_holding AS funds, sp.funds_prev, sp.funds_pct, sp.filers_pct, sp.vs_tide_pts,
                   sp.streak, sp.direction, sp.net_flow, sp.price_pct, sp.median_price,
                   cf.free_cash_flow, cf.prior_free_cash_flow, cf.lower_free_cash_flow,
                   cf.fiscal_end, cf.prior_fiscal_end, cf.entity_name,
                   sp.median_price * cf.diluted_shares AS market_value,
                   cf.lower_free_cash_flow / (sp.median_price * cf.diluted_shares) AS fcf_yield
            {_from(con, known_by)}
            {price_join}
            WHERE {_WHERE}
              AND {_COMPARABLE} AND {_SHARES_AGREE}
              AND sp.vs_tide_pts > 0 AND sp.direction > 0 AND sp.streak >= ? AND sp.net_flow > 0
              AND cf.free_cash_flow > 0 AND cf.prior_free_cash_flow > 0
        )
        WHERE fcf_yield >= ?
        ORDER BY {order}, cusip
        LIMIT ?
        """,
        [period, minimum, minimum, min_streak, min_yield, limit],
    )
    for r in found:
        r["priced"] = priced_in(r["vs_market_pts"])
    return found


def priced_in(vs_market_pts: float | None) -> str | None:
    """Where a pick's price stands against the market since the quarter funds bought in:
    "lagging" (PRICE_LAG_PTS or more behind: the flow may not be priced in yet), "in line",
    or "ahead"; None without prices."""
    if vs_market_pts is None:
        return None
    if vs_market_pts <= -PRICE_LAG_PTS:
        return "lagging"
    return "ahead" if vs_market_pts >= PRICE_LAG_PTS else "in line"


_PRICE_COLUMNS = (
    "pr.since_start_pct, pr.quarter_pct, pr.latest_close, pr.latest_day, pr.vs_market_pts, "
    "pr.market_since_start_pct, pr.price_source, sp.net_flow / NULLIF(pr.dollar_volume, 0) AS flow_share"
)


def _price_join(con) -> tuple[str, str]:
    """The stock_prices columns and join for a query on stock_periods as `sp`, or NULLs in a
    database built before daily prices were added."""
    if not has_prices(con):
        return (
            "NULL AS since_start_pct, NULL AS quarter_pct, NULL AS latest_close, NULL AS latest_day, "
            "NULL AS vs_market_pts, NULL AS market_since_start_pct, NULL AS price_source, NULL AS flow_share",
            "",
        )
    return _PRICE_COLUMNS, "LEFT JOIN stock_prices pr ON pr.cusip = sp.cusip AND pr.period = sp.period"


def coverage(con, period: date, minimum: int, known_by: date | None = None) -> dict:
    """How many stocks were compared, how many have two comparable years of cash
    flow, how many are banks, insurers or lenders, and how many failed the share checks."""
    compared = scalar(
        con,
        """
        SELECT count(*) FROM stock_periods sp JOIN stocks s ON s.cusip = sp.cusip
        WHERE sp.period = ? AND sp.funds_holding >= ? AND sp.funds_prev >= ? AND s.kind = 'stock'
        """,
        [period, minimum, minimum],
    )
    with_cash_flow, financial, shares_differ = con.execute(
        f"""
        SELECT count(*) FILTER (WHERE {_COMPARABLE}),
               count(*) FILTER (WHERE cf.financial),
               count(*) FILTER (WHERE {_COMPARABLE} AND NOT ({_SHARES_AGREE}))
        {_from(con, known_by)}
        WHERE {_WHERE}
        """,
        [period, minimum, minimum],
    ).fetchone() or (0, 0, 0)
    return {
        "compared": compared,
        "with_cash_flow": with_cash_flow,
        "financial": financial,
        "shares_differ": shares_differ,
    }


@dataclass
class _Period:
    period: date
    prev_period: date | None
    deadline: date
    data_through: date


def default_period(con) -> date | None:
    """The period the list opens on (choose_period), read from the model's periods table."""
    if not has_table(con, "periods"):
        return None
    found = [
        _Period(*r)
        for r in con.execute(
            "SELECT period, prev_period, deadline, data_through FROM periods ORDER BY period"
        ).fetchall()
    ]
    if not any(p.prev_period is not None for p in found):
        return None
    return choose_period(found).period


# Every update ends by saving the list it opens on with the default settings, so a later
# run can say what entered and left. History, not model: the build never drops it.
RUNS_DDL = """
CREATE TABLE IF NOT EXISTS accumulate_runs (
    run_at        TIMESTAMP NOT NULL,  -- UTC
    period        DATE NOT NULL,
    rank          INTEGER NOT NULL,    -- 1 is the highest free cash flow yield
    cusip         VARCHAR NOT NULL,
    ticker        VARCHAR,
    name_filed    VARCHAR,
    name_mixed    VARCHAR,
    fcf_yield     DOUBLE,
    funds         INTEGER,
    vs_tide_pts   DOUBLE,
    streak        INTEGER,
    vs_market_pts DOUBLE,
    rules         VARCHAR NOT NULL     -- the thresholds the list was drawn with, as JSON
)
"""


def save_run(con, now: datetime) -> int:
    """Save the list with the default settings as this run's. Returns how many picks it holds;
    0, and nothing saved, while the model has no financials or no period to compare."""
    period = default_period(con)
    if period is None or not has_cash_flows(con) or not has_table(con, "stock_periods"):
        return 0
    found = picks(con, period, MIN_FUNDS, MIN_YIELD, MIN_STREAK, by="yield", limit=10_000)
    rules = json.dumps({"min_funds": MIN_FUNDS, "min_yield": MIN_YIELD, "min_streak": MIN_STREAK})
    run_at = now.astimezone(UTC).replace(tzinfo=None)
    con.execute(RUNS_DDL)
    if found:
        con.executemany(
            "INSERT INTO accumulate_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                [
                    run_at,
                    period,
                    rank,
                    r["cusip"],
                    r["ticker"],
                    r["name_filed"],
                    r["name_mixed"],
                    r["fcf_yield"],
                    r["funds"],
                    r["vs_tide_pts"],
                    r["streak"],
                    r["vs_market_pts"],
                    rules,
                ]
                for rank, r in enumerate(found, start=1)
            ],
        )
    else:  # an empty list is a result too: a marker row keeps the run
        con.execute(
            "INSERT INTO accumulate_runs VALUES (?, ?, 0, '', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?)",
            [run_at, period, rules],
        )
    return len(found)


def saved_runs(con) -> list[datetime]:
    """When each saved run was made, oldest first."""
    if not has_table(con, "accumulate_runs"):
        return []
    return [r[0] for r in con.execute("SELECT DISTINCT run_at FROM accumulate_runs ORDER BY run_at").fetchall()]


def latest_count(con) -> int:
    """How many picks the latest saved run holds; 0 with no run."""
    runs = saved_runs(con)
    if not runs:
        return 0
    return int(scalar(con, "SELECT count(*) FROM accumulate_runs WHERE run_at = ? AND rank > 0", [runs[-1]]))


@dataclass
class RunChange:
    """What changed between the two latest saved runs."""

    run_at: datetime
    previous_at: datetime
    period: date
    previous_period: date
    entered: list[dict]  # picks of the latest run that the run before did not have, by rank
    left: list[dict]  # picks of the run before that the latest run does not have, by their old rank
    stayed: int
    rules_changed: bool  # the thresholds differ, so some moves come from the rule, not the data

    @property
    def new_period(self) -> bool:
        return self.period != self.previous_period


def last_change(con) -> RunChange | None:
    """The change from the run before the latest to the latest, or None with fewer than two runs."""
    runs = saved_runs(con)
    if len(runs) < 2:
        return None
    previous_at, run_at = runs[-2], runs[-1]

    def picks_of(when: datetime) -> tuple[date, str, dict[str, dict]]:
        found = rows(con, "SELECT * FROM accumulate_runs WHERE run_at = ? ORDER BY rank", [when])
        return found[0]["period"], found[0]["rules"], {r["cusip"]: r for r in found if r["rank"] > 0}

    period, rules, latest = picks_of(run_at)
    previous_period, previous_rules, before = picks_of(previous_at)
    return RunChange(
        run_at=run_at,
        previous_at=previous_at,
        period=period,
        previous_period=previous_period,
        entered=[r for c, r in latest.items() if c not in before],
        left=[r for c, r in before.items() if c not in latest],
        stayed=sum(1 for c in latest if c in before),
        rules_changed=rules != previous_rules,
    )
