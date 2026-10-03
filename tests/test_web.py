"""Phase 3: the "Look up a stock" page, rendered for many kinds of stock."""

import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from thirteenf.web.app import app

pytestmark = pytest.mark.data

WEB = Path(__file__).resolve().parents[1] / "src" / "thirteenf" / "web"
JUNK = re.compile(r"\bNone\b|\bnan\b|Traceback|\{\{|\{%|\(—\)")


@pytest.fixture(scope="module")
def client(con):  # con: skip when there is no data
    return TestClient(app)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _period_rows(html: str) -> dict[str, int]:
    """Period label -> funds holding, from the 'Every filing period' table."""
    table = html.split("Every filing period", 1)[1].split("</table>", 1)[0]
    rows = {}
    for row in re.findall(r"<tr>(.*?)</tr>", table, re.S):
        cells = [_text(c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if cells:
            rows[cells[0]] = int(cells[1].replace(",", ""))  # Period | Funds holding | ...
    return rows


def _label(period: date) -> str:
    return f"Q{(period.month - 1) // 3 + 1} {period.year}"


def _check_page(client, con, cusip: str) -> str:
    response = client.get(f"/stock/{cusip}")
    assert response.status_code == 200, cusip
    html = response.text
    text = _text(html)
    junk = JUNK.search(text)
    assert junk is None, (cusip, junk and text[max(0, junk.start() - 80): junk.end() + 80])
    # Every period on the page agrees with the model, and the page reaches the latest period.
    expected = {
        _label(period): funds
        for period, funds in con.execute(
            "SELECT period, funds_holding FROM holders WHERE cusip = ?", [cusip]
        ).fetchall()
    }
    rows = _period_rows(html)
    for label, funds in rows.items():
        assert funds == expected.get(label, 0), (cusip, label)
    latest = con.execute("SELECT max(period) FROM periods").fetchone()[0]
    assert _label(latest) in rows
    if _label(latest) in expected:
        assert f"Funds holding, {latest:%b} {latest.day}, {latest.year}" in text
    assert html.count('class="app-chart__bar') == sum(1 for f in rows.values() if f > 0)
    assert 'id="method"' in html
    return html


@pytest.mark.parametrize("ticker", ["SHOP", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"])
def test_reference_stocks_render_and_track_the_reference(client, con, reference, ticker):
    rows = [r for r in reference if r["ticker"] == ticker]
    html = _check_page(client, con, rows[0]["cusip"])
    page = _period_rows(html)
    rows.sort(key=lambda r: r["period"])
    for prev, cur in zip(rows, rows[1:]):
        ref_pct = cur["filings"] / prev["filings"] - 1
        our_pct = page[_label(cur["period"])] / page[_label(prev["period"])] - 1
        assert abs(our_pct - ref_pct) * 100 <= 2.0, (ticker, cur["period"])


def _stock_near(con, funds: int, exclude: set[str]) -> str:
    return con.execute(
        f"""
        SELECT h.cusip FROM holders h
        WHERE h.period = (SELECT max(period) FROM periods)
          AND h.cusip NOT IN ({",".join("?" * len(exclude))})
        ORDER BY abs(h.funds_holding - ?), h.cusip LIMIT 1
        """,
        [*exclude, funds],
    ).fetchone()[0]


def test_stocks_of_every_size_render(client, con, reference):
    exclude = {r["cusip"] for r in reference}
    picked = []
    for size in (5000, 1000, 300, 100, 30):
        picked.append(_stock_near(con, size, exclude | set(picked)))
    funds = [
        con.execute(
            "SELECT funds_holding FROM holders WHERE period = (SELECT max(period) FROM periods) AND cusip = ?",
            [cusip],
        ).fetchone()[0]
        for cusip in picked
    ]
    assert min(funds) < 50
    for cusip in picked:
        _check_page(client, con, cusip)


def test_a_new_listing_renders(client, con):
    """SpaceX lists in Q2 2026. One filer reported it privately in 2025; the
    page starts at the listing."""
    html = _check_page(client, con, "84615Q103")
    assert "No 13F filer reported it at Mar 31, 2026." in _text(html)
    assert list(_period_rows(html)) == ["Q2 2026"]


def test_a_split_passes_the_share_check(client, con):
    """Broadcom split 10 for 1 in July 2024: shares jump tenfold, value does not."""
    check = con.execute(
        "SELECT share_check FROM stock_periods WHERE cusip = '11135F101' AND period = DATE '2024-09-30'"
    ).fetchone()[0]
    assert check == "ok"
    html = _check_page(client, con, "11135F101")
    assert "Shares outran value" not in html


def test_an_earlier_cusip_opens_the_stock(client, con):
    response = client.get("/stock/438516106", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/stock/438516205?from=438516106"
    html = _check_page(client, con, "438516205")
    assert "Funds moved from CUSIP 438516106 to 438516205 in Q2 2026" in _text(html)


def test_search_finds_a_name_or_a_cusip(client):
    response = client.get("/stock?q=shopify", follow_redirects=False)
    assert response.status_code == 303 or "/stock/82509L107" in response.text
    response = client.get("/stock?q=82509L107", follow_redirects=False)
    assert response.headers["location"] == "/stock/82509L107"
    assert client.get("/stock?q=zzzz-no-such-company").status_code == 200


def test_unknown_cusip_is_a_404(client):
    assert client.get("/stock/ZZZZZZZZ9").status_code == 404


def test_dark_theme_comes_from_the_cookie(client):
    client.cookies.set("tf_theme", "dark")
    try:
        assert '<html lang="en" data-theme="dark">' in client.get("/stock/82509L107").text
    finally:
        client.cookies.clear()
    assert '<html lang="en" data-theme="light">' in client.get("/stock/82509L107").text


def test_no_hard_coded_colors():
    """Colors come only from the design system's variables."""
    color = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    for path in [*WEB.glob("templates/*.html"), WEB / "static" / "app.css", WEB / "charts.py", WEB / "story.py"]:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = re.sub(r'href="#\w+"', "", line)
            assert not color.search(stripped), f"{path.name}: {line.strip()}"
