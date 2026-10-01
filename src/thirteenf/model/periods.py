"""Filing periods (quarter ends) and their 13F deadlines."""

from __future__ import annotations

from datetime import date, timedelta

FILING_DAYS = 45


def quarter_end(year: int, quarter: int) -> date:
    return {1: date(year, 3, 31), 2: date(year, 6, 30), 3: date(year, 9, 30), 4: date(year, 12, 31)}[quarter]


def quarter_of(day: date) -> tuple[int, int]:
    return day.year, (day.month - 1) // 3 + 1


def next_quarter_end(day: date) -> date:
    year, q = quarter_of(day)
    return quarter_end(year + (q == 4), 1 if q == 4 else q + 1)


def previous_quarter_end(day: date) -> date:
    year, q = quarter_of(day)
    return quarter_end(year - (q == 1), 4 if q == 1 else q - 1)


def label(period: date) -> str:
    """Q2 2026"""
    year, q = quarter_of(period)
    return f"Q{q} {year}"


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    last = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def federal_holidays(year: int) -> set[date]:
    mon, thu = 0, 3
    return {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, mon, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, mon, 3),  # Washington's Birthday
        _last_weekday(year, 5, mon),  # Memorial Day
        _observed(date(year, 6, 19)),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, mon, 1),  # Labor Day
        _nth_weekday(year, 10, mon, 2),  # Columbus Day
        _observed(date(year, 11, 11)),
        _nth_weekday(year, 11, thu, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),
    }


def filing_deadline(period: date) -> date:
    """45 days after the quarter end, moved to the next business day."""
    day = period + timedelta(days=FILING_DAYS)
    while day.weekday() >= 5 or day in federal_holidays(day.year):
        day += timedelta(days=1)
    return day


def first_full_period(first_window_start: date) -> date:
    """The first quarter whose deadline falls inside the loaded filing windows."""
    period = previous_quarter_end(first_window_start)
    while filing_deadline(period) < first_window_start:
        period = next_quarter_end(period)
    return period


def periods_between(first: date, last: date) -> list[date]:
    out = []
    period = first
    while period <= last:
        out.append(period)
        period = next_quarter_end(period)
    return out
