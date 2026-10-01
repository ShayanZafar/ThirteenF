from datetime import date

from thirteenf.model import periods as P


def test_deadline_is_45_days_after_quarter_end():
    assert P.filing_deadline(date(2026, 6, 30)) == date(2026, 8, 14)


def test_deadline_moves_past_weekend_and_holiday():
    # Feb 14, 2026 is a Saturday and Feb 16 is Washington's Birthday.
    assert P.filing_deadline(date(2025, 12, 31)) == date(2026, 2, 17)
    # Nov 14, 2026 is a Saturday.
    assert P.filing_deadline(date(2026, 9, 30)) == date(2026, 11, 16)


def test_first_full_period_of_the_first_window():
    assert P.first_full_period(date(2024, 6, 1)) == date(2024, 6, 30)


def test_labels_and_steps():
    assert P.label(date(2026, 6, 30)) == "Q2 2026"
    assert P.previous_quarter_end(date(2025, 3, 31)) == date(2024, 12, 31)
    assert P.periods_between(date(2024, 6, 30), date(2025, 3, 31)) == [
        date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31), date(2025, 3, 31)
    ]
