"""A manager's page and its CSV: every position in a 13F report, each against the report before.

docs/13f-data.md, "Changes between two periods, per manager": opened, sold out, added or
trimmed, held; a manager's first 13F has no changes, and "weight in book" is a position's
value as a share of the reported portfolio. The pure pieces on their own, the pages on the
made-up data set and the page in a browser; none of them need the SEC download
(tests/test_flows.py checks Alphabet's real book against 13f.info)."""

import csv
import io
import re
from datetime import date
from pathlib import Path

import minidata
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Page, expect

from thirteenf.web import data, story
from thirteenf.web.app import app

Q3, Q4 = date(2024, 9, 30), date(2024, 12, 31)
PERIODS = {date(2024, 6, 30): 0, Q3: 1, Q4: 2}  # minidata.WINDOWS, in order
CIK = 135  # at Q4 2024: added to Apple, opened Microsoft, Amazon and QQQ, sold out of Nvidia


# --- One module at a time --------------------------------------------------------------


@pytest.mark.parametrize(
    ("shares_prev", "shares_now", "filed_before", "flagged", "converted", "action"),
    [
        (None, 500, True, False, False, "new"),  # opened: no shares last period, shares now
        (500, None, True, False, False, "exit"),  # sold out: shares last period, none now
        (500, 800, True, False, False, "add"),
        (500, 200, True, False, False, "trim"),
        (500, 500, True, False, False, "hold"),
        (1000, 1004, True, False, True, "hold"),  # converted from an old CUSIP: within 1% is held
        (1000, 1004, True, False, False, "add"),
        (None, 500, False, False, False, "first"),  # a first 13F: its positions may be years old
        (500, 800, True, True, False, "check"),  # a report the implied-price check flags
    ],
)
def test_what_a_manager_did_with_a_position(shares_prev, shares_now, filed_before, flagged, converted, action):
    assert data._action(shares_prev, shares_now, filed_before, flagged, converted) == action


def _book(**overrides) -> data.Book:
    fields = dict(
        cik=1, name="Test Manager", period=Q4, prev_period=Q3, value=1000.0, positions=4, value_prev=900.0,
        positions_prev=4, filed=date(2025, 2, 14), accession="0000000001-25-000001", first_filing=False,
    )  # fmt: skip
    return data.Book(**(fields | overrides))


def _position(action: str, value_now: float | None, value_prev: float | None) -> data.Position:
    shares_now, shares_prev = (value_now or 0) / 10 or None, (value_prev or 0) / 10 or None
    return data.Position(
        cusip="X", ticker="", name=action, title_of_class=None, kind="stock", action=action,
        shares_prev=shares_prev, shares_now=shares_now, value_prev=value_prev, value_now=value_now,
        weight_prev=None, weight_now=value_now / 1000 if value_now else None, flow=None,
    )  # fmt: skip


def test_the_answer_counts_what_a_manager_opened_added_trimmed_and_exited():
    positions = [
        _position("new", 400, None),
        _position("add", 300, 200),
        _position("trim", 200, 300),
        _position("hold", 100, 100),
        _position("exit", None, 300),
    ]
    assert story.manager_answer(_book(), positions, "Test Manager") == (
        "A concentrated book: 4 positions, the ten largest are 100% of it. "
        "In Q4 they opened 1 position, added to 1, trimmed 1 and exited 1."
    )
    # A first 13F, or a report the data set holds only part of, has no changes to count.
    for book in (_book(first_filing=True), _book(complete=False), _book(complete_before=False)):
        answer = story.manager_answer(book, positions, "Test Manager")
        assert answer == "A concentrated book: 4 positions, the ten largest are 100% of it."
    assert story.manager_answer(_book(), [], "Test Manager") == (
        "Test Manager reported no share positions for Dec 31, 2024."
    )


# --- The pages on the made-up data set --------------------------------------------------


def _held(cik: int, period: date) -> dict[str, int]:
    """CUSIP -> shares, as tests/minidata.py writes the manager's report."""
    i = PERIODS[period]
    return {c: 1000 * cik + 100 * i for c, (*_, held) in minidata.SECURITIES.items() if cik <= held[i]}


def _value(cusip: str, shares: float) -> float:
    return shares * minidata.SECURITIES[cusip][2]


def _expected_rows(cik: int, period: date, before: date) -> dict[str, dict]:
    now, prev = _held(cik, period), _held(cik, before)
    total = sum(_value(c, s) for c, s in now.items())
    rows = {}
    for cusip in now.keys() | prev.keys():
        shares, shares_prev = now.get(cusip, 0), prev.get(cusip, 0)
        change = "new" if not shares_prev else "exit" if not shares else "add" if shares > shares_prev else "trim"
        rows[cusip] = {
            "value_usd": str(round(_value(cusip, shares))) if shares else "",
            "weight": f"{_value(cusip, shares) / total:.6f}" if shares else "",
            "shares": str(shares),
            "shares_before": str(shares_prev),
            "change": change,
            "net_buying_usd": str(round(_value(cusip, shares - shares_prev))),
        }
    return rows


def test_the_csv_has_every_position_against_the_report_before(mini_db):
    response = TestClient(app).get(f"/manager/{CIK}/positions.csv", params={"period": "2024-12-31"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == f'attachment; filename="13f-{CIK}-2024-12-31.csv"'
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert list(rows[0]) == [
        "ticker", "name", "class", "cusip", "kind", "value_usd", "weight", "shares", "shares_before", "change",
        "net_buying_usd",
    ]  # fmt: skip
    got = {
        r["cusip"]: {k: r[k] for k in ("value_usd", "weight", "shares", "shares_before", "change", "net_buying_usd")}
        for r in rows
    }
    assert got == _expected_rows(CIK, Q4, Q3)
    held = [r for r in rows if int(r["shares"])]
    assert [r["cusip"] for r in rows] == [
        *sorted((r["cusip"] for r in held), key=lambda c: -_value(c, _held(CIK, Q4)[c])),
        "67066G104",  # the exit comes after every holding
    ]
    assert sum(float(r["weight"]) for r in held) == pytest.approx(1.0, abs=1e-5)


def test_the_manager_page_shows_the_book_and_an_earlier_period(mini_db):
    client = TestClient(app)
    html = client.get(f"/manager/{CIK}").text
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    assert "Test Manager 135" in text and "13F holdings, Q4 2024" in text
    assert "In Q4 they opened 3 positions, added to 1, trimmed 0 and exited 1." in text
    assert f'href="/manager/{CIK}/positions.csv?period=2024-12-31"' in html
    assert f"https://www.sec.gov/Archives/edgar/data/{CIK}/" in html
    first = re.sub(
        r"\s+", " ", re.sub(r"<[^>]+>", " ", client.get(f"/manager/{CIK}", params={"period": "2024-06-30"}).text)
    )
    assert "This is their first 13F in this data, so there is no earlier quarter to compare with." in first
    assert client.get("/manager/999999").status_code == 404
    assert client.get("/manager/999999/positions.csv").status_code == 404


def test_the_managers_list_is_largest_first_and_finds_a_name(mini_db):
    client = TestClient(app)
    values = {cik: sum(_value(c, s) for c, s in _held(cik, Q4).items()) for cik in range(1, minidata.MANAGERS + 1)}
    largest = sorted(values, key=lambda cik: -values[cik])[:100]
    html = client.get("/managers").text
    assert [int(c) for c in re.findall(r'href="/manager/(\d+)"', html)] == largest
    assert f"{minidata.MANAGERS} managers filed 13F holdings for Dec 31, 2024." in html
    found = client.get("/managers", params={"q": "manager 135"}).text
    assert re.findall(r'href="/manager/(\d+)"', found) == ["135"]


# --- In the browser -------------------------------------------------------------------


@pytest.mark.ui
def test_a_person_opens_a_manager_and_downloads_the_csv(mini_db, page: Page, tmp_path: Path):
    page.goto("/")
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Managers").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Managers, Q4 2024")
    page.get_by_label("Find a manager").fill("Test Manager 135")
    page.get_by_role("button", name="Find").click()
    page.get_by_role("link", name="Test Manager 135").click()

    expect(page.get_by_role("heading", level=1)).to_have_text("Test Manager 135")
    positions = page.locator("section").filter(has=page.get_by_role("heading", name=re.compile("^Every position")))
    expect(positions.locator("tbody tr")).to_have_count(5)
    expect(positions.locator("tbody tr").last).to_contain_text("67066G104")

    page.get_by_role("combobox", name="Period").select_option(label="Q3 2024 · positions Sep 30")  # submits on change
    expect(page).to_have_url(re.compile(r"period=2024-09-30"))
    expect(positions.locator("tbody tr")).to_have_count(len(_expected_rows(CIK, Q3, date(2024, 6, 30))))

    with page.expect_download() as download:
        page.get_by_role("link", name="Download CSV").click()
    assert download.value.suggested_filename == f"13f-{CIK}-2024-09-30.csv"
    saved = tmp_path / "positions.csv"
    download.value.save_as(saved)
    rows = list(csv.DictReader(io.StringIO(saved.read_text(encoding="utf-8"))))
    assert {r["cusip"]: r["change"] for r in rows} == {
        c: r["change"] for c, r in _expected_rows(CIK, Q3, date(2024, 6, 30)).items()
    }
