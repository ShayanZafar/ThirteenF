"""Phase 5: the Overview page and your watchlist."""

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from thirteenf import config
from thirteenf.web import watchlist
from thirteenf.web.app import app

pytestmark = pytest.mark.data

Q1_2026, Q2_2026 = date(2026, 3, 31), date(2026, 6, 30)


@pytest.fixture()
def client(con, tmp_path, monkeypatch):  # con: skip when there is no data
    """A fresh watchlist in a temporary file, started from config/watchlist.csv."""
    monkeypatch.setattr(config, "WATCHLIST_PATH", tmp_path / "watchlist.csv")
    return TestClient(app)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _watch_rows(html: str) -> dict[str, dict]:
    """CUSIP -> funds holding and change, from the 'Funds holding each stock' table."""
    table = html.split("Funds holding each stock", 1)[1].split("</table>", 1)[0]
    rows = {}
    for row in re.findall(r"<tr>(.*?)</tr>", table, re.S):
        cusip = re.search(r'href="/stock/([0-9A-Z]{9})"', row)
        if not cusip:
            continue
        cells = [_text(c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        change = re.match(r"([+−]?[\d,]+)", cells[2])
        rows[cusip.group(1)] = {
            "funds": int(cells[1].replace(",", "")),
            "change": int(change.group(1).replace(",", "").replace("−", "-").replace("+", "")),
        }
    return rows


def test_the_example_stocks_match_the_reference(client, con, reference):
    html = client.get("/").text
    rows = _watch_rows(html)
    assert len(rows) == 8
    for ref_now in (r for r in reference if r["period"] == Q2_2026):
        ref_before = next(r for r in reference if r["ticker"] == ref_now["ticker"] and r["period"] == Q1_2026)
        ours = rows[ref_now["cusip"]]
        before = ours["funds"] - ours["change"]
        # Phase 2's rule: the change within 2 points, the level within 11%.
        our_pct = ours["funds"] / before - 1
        ref_pct = ref_now["filings"] / ref_before["filings"] - 1
        assert abs(our_pct - ref_pct) * 100 <= 2.0, ref_now["ticker"]
        assert abs(ours["funds"] / ref_now["filings"] - 1) <= 0.11, ref_now["ticker"]
        model = con.execute(
            "SELECT funds_holding FROM holders WHERE cusip = ? AND period = ?", [ref_now["cusip"], Q2_2026]
        ).fetchone()[0]
        assert ours["funds"] == model


def test_a_stock_added_from_search_appears_with_its_numbers(client, con):
    response = client.post("/watchlist/add", data={"q": "92719W207", "back": "/"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/"
    rows = _watch_rows(client.get("/").text)
    funds = con.execute(
        "SELECT funds_holding FROM holders WHERE cusip = '92719W207' AND period = ?", [Q2_2026]
    ).fetchone()[0]
    assert rows["92719W207"]["funds"] == funds
    assert "92719W207" in watchlist.cusips()


def test_a_name_with_many_matches_goes_to_search(client):
    response = client.post("/watchlist/add", data={"q": "honeywell"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/stock?q=honeywell"
    page = client.get("/stock?q=honeywell").text
    assert 'action="/watchlist/add"' in page


def test_add_from_the_stock_page_and_remove(client):
    page = client.get("/stock/438516205").text
    assert "Add to watchlist" in page
    client.post("/watchlist/add", data={"cusip": "438516106", "back": "/stock/438516205"})
    # The replaced CUSIP is stored as the stock's current one.
    assert "438516205" in watchlist.cusips() and "438516106" not in watchlist.cusips()
    assert "On your watchlist" in client.get("/stock/438516205").text
    client.post("/watchlist/remove", data={"cusip": "438516205"})
    assert "438516205" not in watchlist.cusips()


def test_redirects_stay_inside_the_app(client):
    response = client.post("/watchlist/remove", data={"cusip": "X", "back": "https://example.com/"}, follow_redirects=False)
    assert response.headers["location"] == "/"


def test_the_data_check_is_live_from_price_check(client, con):
    html = client.get("/").text
    check = html.split("Data check,", 1)[1].split("</table>", 1)[0]
    for ticker, cusip in (("AAPL", "037833100"), ("MSFT", "594918104"), ("SHOP", "82509L107")):
        left_out = con.execute(
            """
            SELECT count(*) FROM price_check
            WHERE period = ? AND left_out AND cusip IN (SELECT cusip FROM stock_keys WHERE stock = ?)
            """,
            [Q2_2026, cusip],
        ).fetchone()[0]
        row = re.search(rf"<tr>\s*<td><span class=\"tf-ticker\">{ticker}</span></td>(.*?)</tr>", check, re.S).group(1)
        assert f"{left_out:,} report" in _text(row)


def test_a_failing_share_total_is_flagged_not_shown(client, con):
    """Versigent's Q2 2026 share total moved 40+ points beyond its value."""
    assert con.execute(
        "SELECT share_check FROM stock_periods WHERE cusip = 'G9600F104' AND period = ?", [Q2_2026]
    ).fetchone()[0] == "outran"
    client.post("/watchlist/add", data={"cusip": "G9600F104"})
    html = client.get("/").text
    check = html.split("Data check,", 1)[1].split("</table>", 1)[0]
    # The row shows the ticker when OpenFIGI has one, else the name.
    ticker = con.execute("SELECT ticker FROM stocks WHERE cusip = 'G9600F104'").fetchone()[0]
    label = f'<span class="tf-ticker">{ticker.replace("/", ".")}</span>' if ticker else "Versigent"
    row = [r for r in re.findall(r"<tr>(.*?)</tr>", check, re.S) if label in r][0]
    assert "Shares outran value" in row
    assert "→" not in _text(row)  # the failing total itself is not shown
    assert "1 total failed and is not shown" in _text(html)


def test_the_latest_period_is_still_arriving(client, con):
    complete = con.execute("SELECT complete FROM periods WHERE period = ?", [Q2_2026]).fetchone()[0]
    assert not complete  # filings made after Aug 31, 2026 are not in the data yet
    assert "Still arriving" in client.get("/").text
