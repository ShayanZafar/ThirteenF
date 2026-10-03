"""Phase 7: money flow per stock, the typical stock or ETF, and manager pages."""

import csv
import io
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from thirteenf.web import data
from thirteenf.web.app import app

pytestmark = pytest.mark.data

Q4_2025, Q1_2026, Q2_2026 = date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)
ALPHABET_MANAGER, NORGES_BANK = 1652044, 1374170


@pytest.fixture(scope="module")
def client(con):  # con: skip when there is no data
    return TestClient(app)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _moves(con, cusip, period, prev):
    price = con.execute("SELECT median_price FROM holders WHERE cusip = ? AND period = ?", [cusip, period]).fetchone()[0]
    return data.who_moved(con, cusip, period, prev, price)


@pytest.mark.parametrize("cusip", ["037833100", "82509L107", "464287200", "438516205"])
def test_each_managers_moves_add_up_to_the_net_flow(con, cusip):
    moves = _moves(con, cusip, Q2_2026, Q1_2026)
    bought, sold = con.execute(
        "SELECT bought_value, sold_value FROM stock_periods WHERE cusip = ? AND period = ?", [cusip, Q2_2026]
    ).fetchone()
    assert moves.bought == pytest.approx(bought, rel=1e-6)
    assert moves.sold == pytest.approx(sold, rel=1e-6)


def test_first_filers_and_incomplete_reports_are_not_flow(con):
    """Norges Bank's Q1 2026 report holds 1 of its 1,507 holdings in the SEC data set:
    its Apple shares reappearing in Q2 are not buying."""
    moves = _moves(con, "037833100", Q2_2026, Q1_2026)
    assert "NORGES BANK" in moves.incomplete
    assert all(mv.manager != "NORGES BANK" for mv in moves.moves)
    assert all(mv.flow is None for mv in moves.moves if mv.action == "first")
    complete = con.execute(
        "SELECT complete, base_lines, base_declared FROM filings WHERE cik = ? AND period = ?", [NORGES_BANK, Q1_2026]
    ).fetchone()
    assert complete[0] is False and complete[1] < complete[2] / 2


def test_net_flow_follows_shares_held_by_the_same_managers(con):
    """Bought minus sold equals the change in shares among managers that filed both periods."""
    bought, sold, price = con.execute(
        "SELECT c.bought_shares, c.sold_shares, sp.median_price FROM stock_periods sp JOIN changes c USING (cusip, period) "
        "WHERE cusip = '037833100' AND period = ?",
        [Q2_2026],
    ).fetchone()
    same_managers = con.execute(
        """
        WITH both_periods AS (
            SELECT cik FROM filings WHERE period = ? AND lines > 0 AND complete
            INTERSECT SELECT cik FROM filings WHERE period = ? AND lines > 0 AND complete
        ),
        pos AS (
            SELECT p.period, sum(p.shares) AS shares FROM positions p
            WHERE p.cusip = '037833100' AND p.shares > 0 AND NOT p.price_flag
              AND p.cik IN (SELECT cik FROM both_periods) AND p.period IN (?, ?)
              AND p.cik NOT IN (SELECT cik FROM positions WHERE cusip = '037833100' AND price_flag AND period IN (?, ?))
            GROUP BY 1
        )
        SELECT max(shares) FILTER (WHERE period = ?) - max(shares) FILTER (WHERE period = ?) FROM pos
        """,
        [Q2_2026, Q1_2026, Q2_2026, Q1_2026, Q2_2026, Q1_2026, Q2_2026, Q1_2026],
    ).fetchone()[0]
    assert bought - sold == pytest.approx(same_managers, rel=1e-6)


@pytest.mark.parametrize("cusip, kind", [("037833100", "stock"), ("464287200", "etf")])
def test_a_stock_is_compared_with_its_own_kind(con, cusip, kind):
    typical = con.execute(
        "SELECT market_median_pct FROM stock_periods WHERE cusip = ? AND period = ?", [cusip, Q2_2026]
    ).fetchone()[0]
    expected = con.execute(
        """
        SELECT median(sp.funds_pct) FROM stock_periods sp JOIN stocks s USING (cusip)
        WHERE sp.period = ? AND sp.funds_holding >= 100 AND sp.funds_prev >= 100 AND s.kind = ?
        """,
        [Q2_2026, kind],
    ).fetchone()[0]
    assert typical == pytest.approx(expected)


def test_the_stock_page_shows_the_money_flow(client):
    html = client.get("/stock/037833100").text
    text = _text(html)
    assert "Net 13F flow into Apple Inc, by filing period" in text
    assert "Who added, who left, Q2 2026" in text
    assert "Where Apple Inc sits in each book" in text
    assert html.count('class="tf-flow__row"') >= 2
    assert re.search(r'href="/manager/\d+\?period=2026-06-30"', html)
    assert "Vs typical stock, Q2" in text and "market median" not in text.lower()
    # The full list of moves is one click away.
    assert "?moves=all#moves" in html
    assert client.get("/stock/037833100?moves=all").text.count("<tr>") > html.count("<tr>")


def test_conviction_leaves_out_one_position_books(con):
    for holder in data.largest_weights(con, "037833100", Q2_2026, Q1_2026):
        assert holder.positions >= 10
        assert 0 < holder.weight <= 1 and 1 <= holder.rank <= holder.positions


def test_alphabets_book_matches_13f_info(client, con):
    """13f.info's Alphabet Inc. Q1 2026 filing page and its Q4 2025 comparison."""
    found = data.manager_book(con, ALPHABET_MANAGER, Q1_2026)
    book, positions = found
    assert round(book.value / 1000) == 4_015_569
    assert book.positions == 26
    by_ticker = {p.ticker: p for p in positions}
    assert (by_ticker["CME"].shares_now, round(by_ticker["CME"].value_now / 1000), by_ticker["CME"].action) == (3_484_020, 1_029_005, "new")
    assert (by_ticker["PL"].shares_now, by_ticker["PL"].delta, by_ticker["PL"].action) == (35_248_893, 3_306_252, "add")
    assert (by_ticker["RVMD"].delta, by_ticker["RVMD"].action) == (-52_577, "trim")
    assert by_ticker["ASTS"].action == "hold"
    html = client.get(f"/manager/{ALPHABET_MANAGER}?period=2026-03-31").text
    assert "Alphabet Inc." in html and "3,484,020" in html
    assert f"https://www.sec.gov/Archives/edgar/data/{ALPHABET_MANAGER}/" in html


def test_the_csv_has_every_position(client, con):
    response = client.get(f"/manager/{ALPHABET_MANAGER}/positions.csv?period=2026-03-31")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    held = [r for r in rows if int(r["shares"]) > 0]
    assert len(held) == 26
    assert sum(float(r["weight"]) for r in held if r["weight"]) == pytest.approx(1.0, abs=0.001)


def test_an_incomplete_report_says_so(client):
    text = _text(client.get(f"/manager/{NORGES_BANK}?period=2026-03-31").text)
    assert "holds 1 of the 1,507 holdings this report declares" in text


def test_the_managers_list(client, con):
    html = client.get("/managers").text
    first = re.search(r'href="/manager/(\d+)"', html).group(1)
    largest = con.execute(
        "SELECT cik FROM manager_totals WHERE period = ? ORDER BY value DESC NULLS LAST LIMIT 1", [Q2_2026]
    ).fetchone()[0]
    assert int(first) == largest
    found = client.get("/managers?q=vanguard").text
    assert "VANGUARD" in found.upper()


def test_suggestions_include_managers(client):
    found = client.get("/api/suggest", params={"q": "alphabet"}).json()
    assert any(s["url"] == f"/manager/{ALPHABET_MANAGER}" for s in found)
    assert all(s["url"].startswith("/stock/") for s in client.get("/api/suggest", params={"q": "alphabet", "scope": "stocks"}).json())
