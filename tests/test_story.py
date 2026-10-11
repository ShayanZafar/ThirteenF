"""The one-sentence answer for a stock, pinned for each way it can read."""

from datetime import date

from thirteenf.web.data import StockPeriod
from thirteenf.web.story import answer

PERIODS = [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31)]


def period(i: int, funds: int, prev: int | None, streak: int, direction: int | None, **overrides) -> StockPeriod:
    change = None if prev is None else funds - prev
    row = StockPeriod(
        period=PERIODS[i],
        label=f"Q{(PERIODS[i].month - 1) // 3 + 1} {PERIODS[i].year}",
        held=funds > 0,
        funds=funds,
        funds_prev=prev,
        funds_change=change,
        funds_pct=None if change is None or not prev else change / prev,
        filers=7000,
        filers_pct=0.01,
        share_of_filers=None,
        market_median_pct=0.0,
        vs_tide_pts=None,
        vs_median_pts=None,
        shares=None,
        shares_prev=None,
        shares_pct=None,
        value=None,
        value_pct=None,
        price_pct=None,
        share_check="none",
        shares_vs_value_pts=None,
        flagged_rows=0,
        thousands_rows=0,
        median_price=None,
        streak=streak,
        direction=direction,
        prev_period=PERIODS[i - 1] if i > 0 and prev is not None else None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def series(funds: list[int], **latest) -> list[StockPeriod]:
    """Periods with the given fund counts; the streak and direction follow from them."""
    rows: list[StockPeriod] = []
    streak, direction = 0, None
    for i, n in enumerate(funds):
        prev = funds[i - 1] if i > 0 else None
        if prev is not None:
            d = (n > prev) - (n < prev)
            streak = streak + 1 if d == direction else 1
            direction = d
        rows.append(period(i, n, prev, streak, direction))
    for key, value in latest.items():
        setattr(rows[-1], key, value)
    return rows


def test_not_held():
    assert answer(series([5, 6, 0]), "Acme") == (
        "No 13F filer reported shares of Acme at Sep 30, 2025. 6 funds held it at Jun 30, 2025."
    )
    assert answer(series([0]), "Acme") == "No 13F filer reported shares of Acme at Mar 31, 2025."


def test_first_period():
    assert (
        answer(series([1]), "Acme") == "1 fund held Acme at Mar 31, 2025. That is the first filing period in this data."
    )
    rows = series([3], prev_period=date(2024, 12, 31))
    assert answer(rows, "Acme") == "3 funds held Acme at Mar 31, 2025. No 13F filer reported it at Dec 31, 2024."


def test_unchanged():
    assert answer(series([4, 4]), "Acme") == "The same number of funds held Acme at Jun 30, 2025 as at Mar 31: 4."


def test_streaks():
    assert answer(series([10, 9, 8, 7]), "Acme") == (
        "Fewer funds held Acme in each of the last three filing periods: 7 at Dec 31, 2025, "
        "down from a peak of 10 at Mar 31, 2025."
    )
    assert answer(series([2, 3, 4]), "Acme") == (
        "More funds held Acme in each of the last two filing periods: 4 at Sep 30, 2025, "
        "up from a low of 2 at Mar 31, 2025."
    )
    assert answer(series([1, 5, 3, 4, 6]), "Acme") == (
        "More funds held Acme in each of the last two filing periods: 6 at Mar 31, 2026, up from 3 at Sep 30, 2025."
    )


def test_one_period_change_after_a_streak():
    assert answer(series([10, 9, 8, 9]), "Acme") == (
        "More funds held Acme at Dec 31, 2025 than at Sep 30: 9, up 1 (12.5%). It follows two periods with fewer funds."
    )
    assert answer(series([8, 6]), "Acme") == "Fewer funds held Acme at Jun 30, 2025 than at Mar 31: 6, down 2 (25.0%)."


def test_shares_sentence():
    shares = {"shares": 1_200_000, "shares_prev": 1_000_000, "share_check": "ok"}
    assert answer(series([8, 6], shares_pct=0.2, **shares), "Acme").endswith(
        " The shares those funds hold rose 20%: 1.20M, against 1.00M in March."
    )
    assert answer(series([8, 6], shares_pct=-0.2, **shares), "Acme").endswith(
        " hold fell 20%: 1.20M, against 1.00M in March."
    )
    assert answer(series([8, 6], shares_pct=0.005, **shares), "Acme").endswith(
        " hold barely moved: 1.20M, against 1.00M in March."
    )
    outran = series([8, 6], shares=1, share_check="outran", shares_vs_value_pts=-42.4)
    assert answer(outran, "Acme").endswith(
        " Their share total for Q2 2025 moved 42 points beyond its value, so it is not shown until checked."
    )
