"""Would the Accumulate list have beaten the market? Each past quarter's list, drawn as it
could have been then, held until the next list came out, against SPY over the same days.

For each period with a period before it:

- the list date is the first day the period's list could be read (accumulate.list_date);
- the list is the rule with its default settings, on the financials known by that day
  (accumulate.picks with known_by), never later ones;
- each pick is bought at the first close on or after the list date and sold at the last
  close on or before the next period's list date, or the latest close for the newest list
  (marked open); the quarter's return is the plain average of its picks with prices;
- the market is SPY (prices.MARKET) over the same two dates.

Same days for every pick: a pick with no close within PRICE_LOOKBACK_DAYS after the list date
has no comparable price. A pick whose prices end more than PRICE_LOOKBACK_DAYS before the exit
(delisted, acquired, or no longer fetched) keeps its return to its last close and is held as
cash after it, so a stock that fell and was delisted still counts against the list, and is
marked ended. A quarter enters the totals only when at least MIN_PRICED_SHARE of its picks
have prices: the missing ones are most often the losers.

What it cannot see, said on the page: picks with no daily prices at all, late 13F filings and
amendments that came in after the list date, and restated financials. With two to three years
of daily prices it covers a handful of quarters: a check that the list is not worse than the
market, not proof that it is better.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from thirteenf.ingest.prices import MARKET, symbol_key
from thirteenf.model.build import PRICE_LOOKBACK_DAYS
from thirteenf.model.read import has_table
from thirteenf.signals import accumulate

# The share of a quarter's picks that must have prices for the quarter to count in the totals.
MIN_PRICED_SHARE = 0.9


@dataclass
class Quarter:
    period: date
    label: str
    list_date: date
    exit_date: date
    open: bool  # the newest list, still held: measured to the latest close
    picks: list[dict] = field(default_factory=list)  # each with entry, exit and ret (None without prices)
    market_ret: float | None = None

    @property
    def priced(self) -> list[dict]:
        return [p for p in self.picks if p["ret"] is not None]

    @property
    def ret(self) -> float | None:
        priced = self.priced
        return sum(p["ret"] for p in priced) / len(priced) if priced else None

    @property
    def excess(self) -> float | None:
        return None if self.ret is None or self.market_ret is None else self.ret - self.market_ret

    @property
    def beat(self) -> int | None:
        if self.market_ret is None:
            return None  # no market return to beat: unknown, not zero
        return sum(1 for p in self.priced if p["ret"] > self.market_ret)

    @property
    def complete(self) -> bool:
        """Enough of its picks have prices for its return to count in the totals."""
        return not self.picks or len(self.priced) >= MIN_PRICED_SHARE * len(self.picks)

    @property
    def ended(self) -> int:
        """Picks whose prices ended before the exit, held as cash from their last close."""
        return sum(1 for p in self.priced if p.get("ended"))


@dataclass
class Backtest:
    quarters: list[Quarter]
    through: date | None  # the latest close used

    @property
    def closed(self) -> list[Quarter]:
        return [
            q for q in self.quarters if not q.open and q.complete and q.ret is not None and q.market_ret is not None
        ]

    @property
    def too_few_prices(self) -> list[Quarter]:
        """Past quarters left out of the totals because too few of their picks have prices."""
        return [q for q in self.quarters if not q.open and q.picks and not q.complete]

    def compounded(self) -> tuple[float, float] | None:
        """The list's and the market's returns over the closed quarters, one after another."""
        if not self.closed:
            return None
        mine = market = 1.0
        for q in self.closed:
            mine *= 1 + q.ret  # type: ignore[operator]
            market *= 1 + q.market_ret  # type: ignore[operator]
        return mine - 1, market - 1


def _periods(con) -> list[tuple[date, str, date]]:
    """Periods with a period before them: (period, label, deadline), oldest first."""
    return [
        (r[0], r[1], r[2])
        for r in con.execute(
            "SELECT period, label, deadline FROM periods WHERE prev_period IS NOT NULL ORDER BY period"
        ).fetchall()
    ]


def past_picks(con) -> list[tuple[date, date, list[dict]]]:
    """Each period's list as it could have been read: (period, list date, picks)."""
    if not has_table(con, "periods") or not has_table(con, "stock_cash_flows"):
        return []
    out = []
    for period, _, deadline in _periods(con):
        when = accumulate.list_date(deadline)
        found = accumulate.picks(
            con,
            period,
            accumulate.MIN_FUNDS,
            accumulate.MIN_YIELD,
            accumulate.MIN_STREAK,
            limit=10_000,
            known_by=when,
        )
        out.append((period, when, found))
    return out


def _symbol(pick: dict) -> str | None:
    if not pick["ticker"] or pick.get("ticker_source") == "issuer-name":
        return None
    return symbol_key(pick["ticker"]) or None


def wanted_symbols(con) -> list[str]:
    """Every past list's picks, as symbols, so the price command fetches them too."""
    return list(dict.fromkeys(s for _, _, found in past_picks(con) for p in found if (s := _symbol(p))))


def _close(con, symbol: str, day: date, on_or_after: bool) -> tuple[date, float] | None:
    if on_or_after:
        sql = "SELECT day, close FROM raw_prices WHERE symbol = ? AND day >= ? AND close > 0 ORDER BY day LIMIT 1"
    else:
        sql = "SELECT day, close FROM raw_prices WHERE symbol = ? AND day <= ? AND close > 0 ORDER BY day DESC LIMIT 1"
    row = con.execute(sql, [symbol, day]).fetchone()
    return (row[0], row[1]) if row else None


def _held(con, symbol: str | None, entry: date, exit: date) -> tuple[date, date, float, bool] | None:
    """The first close on or after entry, the last on or before exit, the return between, and
    whether the prices ended early (more than PRICE_LOOKBACK_DAYS before exit: held as cash
    after the last close). None when there is no close within PRICE_LOOKBACK_DAYS of entry:
    a later first close would measure the pick over fewer days than the market."""
    if symbol is None:
        return None
    bought = _close(con, symbol, entry, on_or_after=True)
    sold = _close(con, symbol, exit, on_or_after=False)
    if bought is None or sold is None or sold[0] <= bought[0]:
        return None
    if (bought[0] - entry).days > PRICE_LOOKBACK_DAYS:
        return None
    ended = (exit - sold[0]).days > PRICE_LOOKBACK_DAYS
    return bought[0], sold[0], sold[1] / bought[1] - 1, ended


def run(con) -> Backtest:
    """Every past list against the market, as far as the daily prices reach."""
    if not has_table(con, "raw_prices"):
        return Backtest([], None)
    through = con.execute("SELECT max(day) FROM raw_prices WHERE symbol = ?", [MARKET]).fetchone()
    latest = through[0] if through else None
    if latest is None:
        return Backtest([], None)
    labels = {p: label for p, label, _ in _periods(con)}
    lists = [(p, when, found) for p, when, found in past_picks(con) if when <= latest]
    quarters = []
    for i, (period, when, found) in enumerate(lists):
        is_open = i == len(lists) - 1
        exit_date = latest if is_open else lists[i + 1][1]
        quarter = Quarter(period, labels[period], when, exit_date, is_open)
        market = _held(con, MARKET, when, exit_date)
        quarter.market_ret = market[2] if market else None
        for p in found:
            held = _held(con, _symbol(p), when, exit_date)
            quarter.picks.append(
                p
                | {
                    "entry": held[0] if held else None,
                    "exit": held[1] if held else None,
                    "ret": held[2] if held else None,
                    "ended": held[3] if held else False,
                }
            )
        quarters.append(quarter)
    return Backtest(quarters, latest)
