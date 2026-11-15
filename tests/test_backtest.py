"""The backtest (thirteenf.signals.backtest): each past Accumulate list drawn as it could have
been read then, on the financials known by that day, held until the next list, against SPY."""

from __future__ import annotations

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Page, expect
from test_accumulate import MSFT, accumulate_db  # noqa: F401  (the fixture: made-up financials and tickers)

from thirteenf.db import connect
from thirteenf.ingest import prices
from thirteenf.model import build
from thirteenf.signals import accumulate, backtest
from thirteenf.signals.backtest import Backtest, Quarter
from thirteenf.web import story
from thirteenf.web.app import app

Q3, Q4 = date(2024, 9, 30), date(2024, 12, 31)
CLOSES = {  # SPY up 11% and the pick up 20% while the Q3 list was held; then 8.1% and 10%
    "SPY": {"2024-12-16": 100, "2025-03-14": 111, "2025-04-01": 120},
    "T594": {"2024-12-16": 50, "2025-03-14": 60, "2025-04-01": 66},
}


# --- Unit ------------------------------------------------------------------------------------


def test_a_list_can_be_read_two_weeks_after_its_deadlines_month_ends():
    assert accumulate.list_date(date(2024, 8, 14)) == date(2024, 9, 14)
    assert accumulate.list_date(date(2025, 2, 14)) == date(2025, 3, 14)
    assert accumulate.list_date(date(2024, 12, 2)) == date(2025, 1, 14)


def test_a_quarter_averages_its_picks_and_the_closed_ones_compound():
    q1 = Quarter(Q3, "Q3 2024", date(2024, 12, 14), date(2025, 3, 14), False, market_ret=0.1)
    q1.picks = [{"ret": 0.2}, {"ret": 0.0}]
    q2 = Quarter(Q4, "Q4 2024", date(2025, 3, 14), date(2025, 4, 1), True, market_ret=0.05)
    q2.picks = [{"ret": 0.5}]
    assert q1.ret == pytest.approx(0.1) and q1.excess == pytest.approx(0.0) and q1.beat == 1
    result = Backtest([q1, q2], date(2025, 4, 1))
    assert result.closed == [q1]  # the open one is left out of the totals
    assert result.compounded() == pytest.approx((0.1, 0.1))


def test_a_quarter_with_too_few_priced_picks_is_left_out_of_the_totals():
    q1 = Quarter(Q3, "Q3 2024", date(2024, 12, 14), date(2025, 3, 14), False, market_ret=0.1)
    q1.picks = [{"ret": 0.2}] * 9 + [{"ret": None}]  # 9 of 10 priced: counts
    q2 = Quarter(Q4, "Q4 2024", date(2025, 3, 14), date(2025, 6, 14), False, market_ret=0.05)
    q2.picks = [{"ret": 0.5}, {"ret": 0.5}, {"ret": None}]  # 2 of 3: the missing one may be a loser
    result = Backtest([q1, q2], date(2025, 6, 14))
    assert result.closed == [q1] and result.too_few_prices == [q2]
    text = story.backtest_answer(result)
    assert "1 past list is left out: too few of their picks have prices" in text


def test_without_a_market_return_no_pick_is_counted_as_beating_it_or_not():
    q = Quarter(Q3, "Q3 2024", date(2024, 12, 14), date(2025, 3, 14), False, picks=[{"ret": 0.2}])
    assert q.beat is None  # unknown, never "0 of 1"


def test_the_answer_says_how_many_quarters_and_that_it_is_no_proof():
    q1 = Quarter(Q3, "Q3 2024", date(2024, 12, 14), date(2025, 3, 14), False, market_ret=0.11)
    q1.picks = [{"ret": 0.2}]
    text = story.backtest_answer(Backtest([q1], date(2025, 4, 1)))
    assert text.startswith("Held from one list to the next, the past 1 list returned +20.0% against +11.0% for SPY")
    assert "beating it in 1 of 1 quarter." in text and "not proof" in text
    assert story.backtest_answer(Backtest([], None)).startswith("No past list can be checked yet")


# --- Integration -----------------------------------------------------------------------------


@pytest.fixture
def backtest_db(accumulate_db, monkeypatch):  # noqa: F811
    """The made-up data with a one-period streak (so Q3 2024 has a list too), each fiscal year
    known 30 days after it ends, and daily closes for SPY and Microsoft's made-up ticker."""
    accumulate_db()
    monkeypatch.setattr(accumulate, "MIN_STREAK", 1)
    with connect() as con:
        con.execute("UPDATE stock_cash_flows_history SET known_from = fiscal_end + INTERVAL 30 DAY")
        con.execute(prices.RAW_DDL)
        for symbol, closes in CLOSES.items():
            for day, close in closes.items():
                con.execute(
                    "INSERT INTO raw_prices VALUES (?, ?, ?, ?, ?, ?, 1000, 'stooq', ?)",
                    [symbol, day, close, close, close, close, f"{symbol}.csv"],
                )


def test_an_earlier_list_uses_only_the_financials_known_when_it_came_out(accumulate_db):  # noqa: F811
    accumulate_db()  # each fiscal year known 90 days after it ends
    with connect() as con:
        assert [p["cusip"] for p in accumulate.picks(con, Q3, 100, 0.05, 1)] == [MSFT]  # with today's financials
        # On Dec 14, 2024 the fiscal year to Sep 30, 2024 was not out yet, and the one before has
        # no year before it to compare: no stock qualifies.
        assert accumulate.picks(con, Q3, 100, 0.05, 1, known_by=date(2024, 12, 14)) == []
    html = TestClient(app).get("/accumulate", params={"period": Q3.isoformat(), "streak": 1}).text
    assert "Financials as known on Dec 14, 2024, when this list came out" in html
    assert "No stock held by" in html
    assert "Financials as known on" not in TestClient(app).get("/accumulate").text  # the latest list: today's


def test_each_list_is_held_until_the_next_against_spy(backtest_db):
    with connect() as con:
        result = backtest.run(con)
        assert backtest.wanted_symbols(con) == ["T594", "T023"]  # Amazon joins in Q4
    q3, q4 = result.quarters
    assert (q3.list_date, q3.exit_date, q3.open) == (date(2024, 12, 14), date(2025, 3, 14), False)
    assert q3.ret == pytest.approx(0.2) and q3.market_ret == pytest.approx(0.11) and q3.beat == 1
    assert q3.picks[0]["entry"] == date(2024, 12, 16)  # the first close on or after a Saturday
    assert q4.open and q4.ret == pytest.approx(0.1)
    assert result.compounded() == pytest.approx((0.2, 0.11))


def _set_closes(symbol: str, closes: dict[str, float]) -> None:
    with connect() as con:
        con.execute("DELETE FROM raw_prices WHERE symbol = ?", [symbol])
        for day, close in closes.items():
            con.execute(
                "INSERT INTO raw_prices VALUES (?, ?, ?, ?, ?, ?, 1000, 'stooq', ?)",
                [symbol, day, close, close, close, close, f"{symbol}.csv"],
            )


def test_a_pick_whose_prices_end_early_counts_as_cash_after_its_last_close(backtest_db):
    _set_closes("T594", {"2024-12-16": 50, "2025-01-02": 40})  # delisted in January, down 20%
    with connect() as con:
        q3 = backtest.run(con).quarters[0]
    assert q3.picks[0]["ret"] == pytest.approx(-0.2) and q3.picks[0]["ended"] and q3.ended == 1
    assert q3.complete and q3.excess == pytest.approx(-0.31)  # the loss counts, against SPY's full +11%
    assert "1 ended early, then cash" in TestClient(app).get("/accumulate/backtest").text


def test_a_pick_first_priced_long_after_the_list_date_has_no_comparable_price(backtest_db):
    _set_closes("T594", {"2025-03-10": 59, "2025-03-14": 60})  # no close until three months in
    with connect() as con:
        result = backtest.run(con)
    q3 = result.quarters[0]
    assert q3.picks[0]["ret"] is None and not q3.complete
    assert result.closed == [] and result.too_few_prices == [q3]
    html = TestClient(app).get("/accumulate/backtest").text
    assert "Too few to count in the totals" in html and "No past list can be counted yet" in html


def test_an_earlier_list_gives_no_price_verdict_from_todays_prices(backtest_db):
    _set_closes("SPY", {"2024-06-28": 95, **CLOSES["SPY"]})
    _set_closes("T594", {"2024-06-28": 80, **CLOSES["T594"]})  # down a lot since Q2 ended
    with connect() as con:
        con.execute(build.SQL_STOCK_PRICES)
        [today] = accumulate.picks(con, Q3, 100, 0.05, 1)
        [then] = accumulate.picks(con, Q3, 100, 0.05, 1, known_by=date(2024, 12, 14))
    assert today["priced"] == "lagging" and then["priced"] is None
    html = TestClient(app).get("/accumulate", params={"period": Q3.isoformat(), "streak": 1, "by": "price"}).text
    assert "by=price" not in html and "Lagging the market" not in html  # no such ranking or verdict


def test_the_backtest_page_reads_each_list_against_the_market(backtest_db):
    html = TestClient(app).get("/accumulate/backtest").text
    assert "How past Accumulate lists did" in html
    assert "returned +20.0% against +11.0% for SPY" in html
    assert "Still held, to the latest close" in html
    assert re.search(r"Q3 2024</a>.*?T594", html, re.S)


def test_without_prices_the_backtest_page_says_what_it_needs(accumulate_db):  # noqa: F811
    accumulate_db()
    html = TestClient(app).get("/accumulate/backtest").text
    assert "No past list can be checked yet" in html


# --- UI --------------------------------------------------------------------------------------


@pytest.mark.ui
def test_a_person_checks_how_past_lists_did(backtest_db, page: Page):
    page.goto("/accumulate")
    page.get_by_role("link", name="How past lists did against the market").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("How past Accumulate lists did")
    table = page.locator("section").filter(has=page.get_by_role("heading", name="Each list, held until the next"))
    expect(table.locator("tbody tr")).to_have_count(2)
    expect(table.locator("tbody tr").last).to_contain_text("Q3 2024")
    expect(table.locator("tbody tr").last).to_contain_text("+20.0%")
    expect(page.locator("#method")).to_contain_text("at least 90% of its picks have prices")
    table.get_by_role("link", name="Q3 2024").click()  # the past list: no verdict from today's prices
    expect(page.get_by_role("group", name="Rank by")).not_to_contain_text("Price lagging")
