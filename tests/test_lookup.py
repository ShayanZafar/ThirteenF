"""Looking up one stock in a browser: search as you type, the stock's answer, its periods and
who added or left, on the made-up data set with tickers from a stand-in OpenFIGI (the pieces
are tested in tests/test_story.py and tests/test_seams.py; tests/test_web.py renders real stocks)."""

import re

import minidata
import pytest
from conftest import map_mini_tickers
from playwright.sync_api import Page, expect

MSFT, NVDA = "594918104", "67066G104"


@pytest.fixture
def with_tickers(mini_db, monkeypatch):
    map_mini_tickers(monkeypatch)  # common stock ticked T + its first three digits; QQQ an ETF


def _periods(page: Page) -> dict[str, str]:
    """Period -> funds holding, from the stock page's "Every filing period" table."""
    table = page.locator("section").filter(has=page.get_by_role("heading", name="Every filing period"))
    cells = table.locator("tbody tr").evaluate_all(
        "rows => rows.map(r => [...r.querySelectorAll('td')].slice(0, 2).map(c => c.textContent.trim()))"
    )
    return dict(cells)


@pytest.mark.ui
def test_a_person_types_a_name_and_opens_the_stock_from_the_suggestions(with_tickers, page: Page):
    page.goto("/stock")
    page.get_by_role("combobox", name="Search").fill("micro")
    option = page.get_by_role("option", name=re.compile("Microsoft"))
    expect(option).to_contain_text("T594")
    expect(option).to_contain_text("140 funds")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")

    expect(page).to_have_url(re.compile(f"/stock/{MSFT}$"))
    expect(page.get_by_role("heading", level=1)).to_have_text("Microsoft Corp")
    # minidata: 120, 130 and 140 funds at the three quarter ends.
    expect(page.locator(".app-answer").first).to_contain_text(
        "More funds held Microsoft Corp in each of the last two filing periods: 140 at Dec 31, 2024"
    )
    held = minidata.SECURITIES[MSFT][3]
    assert _periods(page) == {"Q4 2024": str(held[2]), "Q3 2024": str(held[1]), "Q2 2024": str(held[0])}

    # Managers 131 to 140 opened positions at Q4; the largest move comes first and opens its book.
    moves = page.locator("section").filter(has=page.get_by_role("heading", name="Who added, who left, Q4 2024"))
    expect(moves.locator("tbody tr").first).to_contain_text("Test Manager 140")
    expect(moves.locator("tbody tr").first).to_contain_text("New")
    moves.get_by_role("link", name="Test Manager 140").first.click()
    expect(page).to_have_url(re.compile(r"/manager/140\?period=2024-12-31$"))
    expect(page.get_by_role("heading", level=1)).to_have_text("Test Manager 140")


@pytest.mark.ui
def test_a_ticker_or_cusip_in_the_lookup_box_opens_the_stock(with_tickers, page: Page):
    page.goto("/stock")
    lookup = page.get_by_role("combobox", name="Look up a stock")
    lookup.fill("T670")
    page.get_by_role("button", name="Look up").click()
    expect(page).to_have_url(re.compile(f"/stock/{NVDA}$"))
    expect(page.get_by_role("heading", level=1)).to_have_text(re.compile("nvidia", re.I))
    # Fewer funds each period: 150, 140, then 130.
    expect(page.locator(".app-answer").first).to_contain_text("Fewer funds held")

    page.goto("/stock")
    page.get_by_role("combobox", name="Look up a stock").fill("zzzz-no-such-company")
    page.get_by_role("button", name="Look up").click()
    expect(page.get_by_role("heading", name=re.compile("^No stock matches"))).to_be_visible()
