"""How fresh each number is and where it came from, as a person sees it in a browser.

The rules (.claude/rules/ui.md, docs/13f-data.md, docs/sources.md): every number shows its
as-of date and source with a freshness stamp; until the next deadline passes, the latest
period is still arriving, with the count filed so far; a ticker from a fallback says which
one, with its date. On the made-up data set: its newest period is Q4 2024, filed through
Feb 28, 2025, before the Q1 2025 deadline, so Q4 2024 is still arriving."""

import re
from datetime import date

import pytest
from conftest import QUIET, FakeFtdSec, ftd_zip_bytes, openfigi_down
from playwright.sync_api import Page, expect

from thirteenf import tickers
from thirteenf.db import connect

MSFT = "594918104"
LATEST = date(2024, 12, 31)


@pytest.fixture
def ftd_tickers(mini_db, monkeypatch, tmp_path):
    """OpenFIGI is down and the SEC's fails-to-deliver data knows Microsoft's symbol."""
    monkeypatch.setenv("SEC_USER_AGENT", "ThirteenF tests@example.com")
    monkeypatch.setattr(tickers.ftd, "FTD_DIR", tmp_path / "ftd")
    name = "cnsfails202409a.zip"
    sec = FakeFtdSec({name: ftd_zip_bytes(name, [("20240904", MSFT, "MSFT", "100", "MICROSOFT CORP", "430.10")])})
    openfigi_down(monkeypatch, [])
    tickers.update_tickers(log=QUIET, fallback=tickers.TickerFallback(connect, QUIET, sec.client))


@pytest.mark.ui
def test_every_page_says_how_old_its_numbers_are_and_where_they_came_from(ftd_tickers, page: Page):
    age = (date.today() - LATEST).days
    for path in ("/", f"/stock/{MSFT}", "/changes", "/accumulate", "/managers"):
        page.goto(path)
        stamps = page.locator(".app-stamps .tf-stamp")
        expect(stamps.filter(has=page.locator("b").get_by_text("13F", exact=True))).to_have_text(
            f"13F·As of Dec 31, 2024·{age}d·Still arriving: 160 managers so far"
        )
        expect(stamps.filter(has_text="Source")).to_have_text(
            "Source·SEC Form 13F data sets, filed through Feb 28, 2025"
        )


@pytest.mark.ui
def test_a_managers_page_says_when_the_report_was_filed(ftd_tickers, page: Page):
    page.goto("/manager/135")
    stamps = page.locator(".app-stamps .tf-stamp")
    expect(stamps).to_have_text(
        [
            f"13F-HR·As of Dec 31, 2024·{(date.today() - LATEST).days}d",
            "Filed·Feb 14, 2025",
            "Source·SEC Form 13F data sets",
        ]
    )


@pytest.mark.ui
def test_a_fallback_ticker_on_a_list_page_says_where_it_came_from(ftd_tickers, page: Page):
    page.goto("/changes")
    row = page.locator("tbody tr").filter(has=page.locator(f"a[href='/stock/{MSFT}']"))
    mark = row.locator(".tf-tag")
    note = "Ticker from the SEC’s fails-to-deliver data, as of Sep 4, 2024"
    expect(mark).to_have_attribute("title", note)
    expect(mark.locator(".sr-only")).to_have_text(note)  # what a screen reader says
    expect(row.locator(".tf-ticker")).to_have_text("MSFT")
    # An earlier period says how old it is too.
    page.get_by_role("combobox", name="Period").select_option(label="Q3 2024 · positions Sep 30")
    expect(page).to_have_url(re.compile(r"period=2024-09-30"))
    stamp = page.locator(".app-stamps .tf-stamp").first
    expect(stamp).to_contain_text("13F·As of Sep 30, 2024")
