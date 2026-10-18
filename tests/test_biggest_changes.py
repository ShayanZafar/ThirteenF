"""Biggest changes: stocks ranked by their change in funds holding against the tide.

docs/13f-data.md: a stock's change against the tide is its percentage change in funds
holding minus the change in all 13F filers, in points; it ranks the page, among stocks
held by at least the minimum number of funds at both dates, on the All, Stocks or ETFs tab.
These run on rows written by hand, on the made-up data set and in a browser, so they never
skip (tests/test_changes.py checks the same page on the real SEC data)."""

import re

import minidata
import pytest
from fastapi.testclient import TestClient
from model_rows import PERIOD, model, stock, stock_period
from playwright.sync_api import Page, expect

from thirteenf.web import data
from thirteenf.web.app import app

A, B, C, D, E, F = "A00000001", "B00000001", "C00000001", "D00000001", "E00000001", "F00000001"


@pytest.fixture
def ranked():
    """All 13F filers grew 5%. A beat that by 5 points and C by 7; B gained funds yet fell
    behind; E lost funds; D was under the minimum before; F is an ETF that beat it by 5."""
    con = model(
        [
            stock(A, "Alpha"),
            stock(B, "Beta"),
            stock(C, "Gamma"),
            stock(D, "Delta"),
            stock(E, "Epsilon"),
            stock(F, "Fund Trust", kind="etf"),
        ],
        [
            stock_period(A, 121, 110, filers_pct=0.05),
            stock_period(B, 206, 200, filers_pct=0.05),
            stock_period(C, 112, 100, filers_pct=0.05),
            stock_period(D, 150, 99, filers_pct=0.05),
            stock_period(E, 270, 300, filers_pct=0.05),
            stock_period(F, 165, 150, filers_pct=0.05),
        ],
    )
    yield lambda **kw: [r["cusip"] for r in data.ranked_changes(con, PERIOD, **({"minimum": 100} | kw))]
    con.close()


def test_the_list_ranks_by_the_change_against_the_tide(ranked):
    rows = dict(by="tide", limit=25)
    assert ranked(**rows, most="added") == [C, A, F]  # A and F tie at +5 pts: by CUSIP
    # B gained funds but fewer than the tide brought: it lost against the tide.
    assert ranked(**rows, most="lost") == [E, B]


def test_ranking_by_the_change_in_funds_counts_funds_alone(ranked):
    assert ranked(by="count", limit=25, most="added") == [F, C, A, B]
    assert ranked(by="count", limit=25, most="lost") == [E]


def test_only_stocks_held_by_the_minimum_at_both_dates_are_ranked(ranked):
    assert D not in ranked(by="count", limit=25, most="added")  # 99 funds before
    assert ranked(by="tide", limit=25, most="added", minimum=110) == [A, F]  # C had 100, then 112
    assert ranked(by="tide", limit=1, most="added") == [C]


def test_a_tab_ranks_one_kind(ranked):
    assert ranked(by="tide", limit=25, most="added", kind="stocks") == [C, A]
    assert ranked(by="tide", limit=25, most="added", kind="etfs") == [F]
    assert ranked(by="tide", limit=25, most="lost", kind="etfs") == []


# --- The page on the made-up data set ---------------------------------------------


def _expected(period: int, minimum: int, most: str) -> list[str]:
    """The ranking worked out from minidata's own counts: every manager files every period,
    so the tide is zero and the change against it is the stock's own change."""
    moves = {}
    for cusip, (*_, held) in minidata.SECURITIES.items():
        now, before = held[period], held[period - 1]
        if now >= minimum and before >= minimum and now != before:
            moves[cusip] = now / before - 1
    chosen = [c for c, pct in moves.items() if (pct > 0) == (most == "added")]
    return sorted(chosen, key=lambda c: (-moves[c] if most == "added" else moves[c], c))


@pytest.mark.parametrize(("period", "minimum"), [("2024-12-31", 100), ("2024-09-30", 100), ("2024-12-31", 130)])
def test_the_page_ranks_the_made_up_data_against_the_tide(mini_db, period, minimum):
    html = TestClient(app).get("/changes", params={"period": period, "min": minimum}).text
    index = {"2024-09-30": 1, "2024-12-31": 2}[period]  # minidata.WINDOWS: Q2, Q3, Q4 2024
    added = html.split("Most funds added", 1)[1].split("Most funds lost", 1)[0]
    lost = html.split("Most funds lost", 1)[1]
    assert re.findall(r'href="/stock/([0-9A-Z]{9})"', added) == _expected(index, minimum, "added")
    assert re.findall(r'href="/stock/([0-9A-Z]{9})"', lost.split("</table>", 1)[0]) == _expected(index, minimum, "lost")
    assert "All 13F filers, Q" in html and "160 managers filed holdings" in html


# --- In the browser -----------------------------------------------------------------


def _rows(page: Page, heading: str):
    section = page.locator("section").filter(has=page.get_by_role("heading", name=re.compile(f"^{heading}")))
    return section.locator("tbody tr a[href^='/stock/']")


def _cusips(page: Page, heading: str) -> list[str]:
    return [
        h.removeprefix("/stock/")
        for h in _rows(page, heading).evaluate_all("els => els.map(e => e.getAttribute('href'))")
    ]


@pytest.mark.ui
def test_a_person_finds_the_biggest_movers_and_opens_one(mini_db, page: Page):
    page.goto("/")
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Biggest changes").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Biggest changes in funds holding, Q4 2024")
    assert _cusips(page, "Most funds added") == _expected(2, 100, "added")
    assert _cusips(page, "Most funds lost") == _expected(2, 100, "lost")

    page.get_by_role("combobox", name="Period").select_option(label="Q3 2024 · positions Sep 30")  # submits on change
    expect(page.get_by_role("heading", level=1)).to_have_text("Biggest changes in funds holding, Q3 2024")
    assert _cusips(page, "Most funds added") == _expected(1, 100, "added")

    # QQQ counts as "other" until OpenFIGI says it is an ETF: the Stocks tab leaves it out.
    page.get_by_role("navigation", name="Kind of security").get_by_role("link", name=re.compile("^Stocks")).click()
    expect(page).to_have_url(re.compile(r"period=2024-09-30.*kind=stocks"))
    assert _cusips(page, "Most funds added") == [c for c in _expected(1, 100, "added") if c != minidata.QQQ]

    _rows(page, "Most funds added").first.click()
    expect(page).to_have_url(re.compile(r"/stock/594918104$"))
    expect(page.get_by_role("heading", level=1)).to_contain_text("Microsoft")
