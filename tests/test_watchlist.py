"""Your watchlist (thirteenf.web.watchlist): a CSV in data/ that starts from the example list
in config/watchlist.csv, and the overview that shows it. The module on its own, the routes on
the made-up data set, and the overview in a browser; none of them need the SEC download."""

import csv
import re

import minidata
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Page, expect

from thirteenf import config
from thirteenf.web import watchlist
from thirteenf.web.app import app

AAPL, MSFT, NVDA, AMZN, QQQ = "037833100", "594918104", "67066G104", "023135106", minidata.QQQ


@pytest.fixture(autouse=True)
def own_watchlist(tmp_path, monkeypatch):
    """Each test keeps its watchlist in a file of its own, never in data/."""
    monkeypatch.setattr(config, "WATCHLIST_PATH", tmp_path / "lists" / "watchlist.csv")
    return config.WATCHLIST_PATH


def _example() -> list[watchlist.Entry]:
    with open(config.WATCHLIST_CSV, newline="", encoding="utf-8") as f:
        return [watchlist.Entry(r["cusip"], r["ticker"], r["name"]) for r in csv.DictReader(f)]


# --- The module ----------------------------------------------------------------------


def test_the_first_look_starts_from_the_example_list(own_watchlist):
    assert not own_watchlist.exists()
    assert watchlist.load() == _example()
    assert own_watchlist.read_text(encoding="utf-8") == config.WATCHLIST_CSV.read_text(encoding="utf-8")


def test_a_stock_is_added_once_by_its_cusip_as_written_in_capitals():
    watchlist.save([])
    added = watchlist.add(" 67066g104 ", ticker="nvda ", name=" NVIDIA ")
    added_again = watchlist.add("67066G104")
    assert (added, added_again) == (True, False)
    assert watchlist.load() == [watchlist.Entry(NVDA, "NVDA", "NVIDIA")]
    assert watchlist.cusips() == {NVDA}


def test_removing_a_stock_keeps_the_others_in_order():
    watchlist.save([watchlist.Entry(c) for c in (AAPL, MSFT, NVDA)])
    removed = watchlist.remove(MSFT.lower())
    removed_again = watchlist.remove(MSFT.lower())
    assert (removed, removed_again) == (True, False)
    assert [e.cusip for e in watchlist.load()] == [AAPL, NVDA]


def test_a_cusip_written_twice_or_blank_shows_once(own_watchlist):
    own_watchlist.parent.mkdir(parents=True)
    own_watchlist.write_text(
        f"ticker,cusip,name\nAAPL,{AAPL},Apple\n,,\nappl, {AAPL.lower()} ,Again\nMSFT,{MSFT},\n", encoding="utf-8"
    )
    assert watchlist.load() == [watchlist.Entry(AAPL, "AAPL", "Apple"), watchlist.Entry(MSFT, "MSFT", "")]


def test_a_changed_cusip_moves_the_entry_and_keeps_what_you_wrote():
    watchlist.save([watchlist.Entry("438516106", "HON", "Honeywell"), watchlist.Entry(AAPL)])
    watchlist.replace("438516106", "438516205")
    assert watchlist.load() == [watchlist.Entry("438516205", "HON", "Honeywell"), watchlist.Entry(AAPL)]
    # When the new CUSIP is already on the list, the old entry just goes.
    watchlist.save([watchlist.Entry("438516106"), watchlist.Entry("438516205", "HON")])
    watchlist.replace("438516106", "438516205")
    assert watchlist.load() == [watchlist.Entry("438516205", "HON")]


def test_a_write_that_fails_leaves_the_old_list_whole(own_watchlist, monkeypatch):
    watchlist.save([watchlist.Entry(AAPL, "AAPL", "Apple")])
    before = own_watchlist.read_bytes()

    def crash(*_):
        raise OSError("disk full")

    monkeypatch.setattr(watchlist.os, "replace", crash)
    with pytest.raises(OSError):
        watchlist.add(MSFT)
    assert own_watchlist.read_bytes() == before


# --- The routes on the made-up data set --------------------------------------------------


def _row(html: str, cusip: str) -> str | None:
    table = html.split("Funds holding each stock", 1)[1].split("</table>", 1)[0]
    found = [r for r in re.findall(r"<tr>(.*?)</tr>", table, re.S) if f'href="/stock/{cusip}"' in r]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", found[0])) if found else None


def test_a_stock_added_by_name_shows_on_the_overview_with_its_funds(mini_db):
    watchlist.save([watchlist.Entry(AAPL, "AAPL", "Apple")])
    client = TestClient(app)
    response = client.post("/watchlist/add", data={"q": "invesco", "back": "/"}, follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/")
    assert watchlist.cusips() == {AAPL, QQQ}
    # minidata: 125 funds held QQQ at Sep 30 and 140 at Dec 31.
    row = _row(client.get("/").text, QQQ)
    assert row is not None and " 140 " in row and "+15" in row and "+12.0%" in row

    client.post("/watchlist/remove", data={"cusip": QQQ, "back": "/"})
    assert _row(client.get("/").text, QQQ) is None and watchlist.cusips() == {AAPL}


def test_stocks_not_in_the_data_are_listed_apart(mini_db):
    html = TestClient(app).get("/").text  # the example list: four of its eight are in minidata
    assert all(_row(html, c) for c in (AAPL, MSFT, NVDA, AMZN))
    missing = re.sub(r"<[^>]+>", " ", html.split("Not in the 13F data:", 1)[1].split("</div>", 1)[0])
    assert re.findall(r"\b(SHOP|GOOGL|META|TSLA)\b", missing) == ["SHOP", "GOOGL", "META", "TSLA"]


# --- In the browser ----------------------------------------------------------------


def _watched(page: Page) -> list[str]:
    table = page.locator("section").filter(has=page.get_by_role("heading", name="Funds holding each stock"))
    hrefs = table.locator("tbody tr a[href^='/stock/']").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    return sorted(h.removeprefix("/stock/") for h in hrefs)


@pytest.mark.ui
def test_a_person_adds_a_stock_from_the_suggestions_and_removes_one(mini_db, page: Page):
    page.goto("/")
    expect(page.get_by_role("heading", level=1)).to_have_text("Your watchlist, Q4 2024")
    assert _watched(page) == sorted([AAPL, MSFT, NVDA, AMZN])

    page.get_by_label("Add a stock").fill("invesco")
    suggestion = page.get_by_role("option", name=re.compile("Invesco", re.I))
    expect(suggestion).to_contain_text("140 funds")
    suggestion.click()
    expect(page).to_have_url(re.compile(r"/$"))
    expect(page.locator("tbody a[href='/stock/46090E103']")).to_be_visible()
    assert _watched(page) == sorted([AAPL, MSFT, NVDA, AMZN, QQQ])

    page.get_by_role("button", name=re.compile(r"^Remove .* from your watchlist$")).first.click()
    expect(page.locator("tbody a[href^='/stock/']")).to_have_count(4)
    assert len(_watched(page)) == 4 and len(watchlist.cusips() & {AAPL, MSFT, NVDA, AMZN, QQQ}) == 4


@pytest.mark.ui
def test_a_person_adds_a_stock_from_its_page(mini_db, page: Page):
    watchlist.save([])
    page.goto(f"/stock/{MSFT}")
    page.get_by_role("button", name="Add to watchlist").click()
    expect(page.get_by_text("On your watchlist")).to_be_visible()
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Overview").click()
    assert _watched(page) == [MSFT]
