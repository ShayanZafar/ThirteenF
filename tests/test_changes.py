"""Phase 4: biggest changes across all stocks."""

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from thirteenf.web.app import app

pytestmark = pytest.mark.data

Q2_2026 = date(2026, 6, 30)


@pytest.fixture(scope="module")
def client(con):  # con: skip when there is no data
    return TestClient(app)


def _lists(html: str) -> dict[str, list[dict]]:
    """Rows of the 'added' and 'lost' tables, in page order."""
    out = {}
    for key, heading in (("added", "Most funds added"), ("lost", "Most funds lost")):
        section = html.split(heading, 1)[1].split("</table>", 1)[0]
        rows = []
        for row in re.findall(r"<tr>(.*?)</tr>", section, re.S):
            cusip = re.search(r'href="/stock/([0-9A-Z]{9})"', row)
            if not cusip:
                continue
            numbers = re.search(r"([\d,]+)</span><span class=\"app-cell__sub tf-num\">from ([\d,]+)", row)
            rows.append(
                {
                    "cusip": cusip.group(1),
                    "funds": int(numbers.group(1).replace(",", "")),
                    "funds_prev": int(numbers.group(2).replace(",", "")),
                }
            )
        out[key] = rows
    return out


def _plain_sql_ranking(con, period: date, minimum: int, by: str, most: str, limit: int) -> list[str]:
    """The same ranking, written directly on holders and filers_total."""
    metric = (
        "(h.funds_holding::DOUBLE / b.funds_holding - ft.filers::DOUBLE / fb.filers) * 100"
        if by == "tide"
        else "h.funds_holding - b.funds_holding"
    )
    order = "DESC" if most == "added" else "ASC"
    sign = ">" if most == "added" else "<"
    return [
        r[0]
        for r in con.execute(
            f"""
            SELECT h.cusip
            FROM holders h
            JOIN periods p ON p.period = h.period
            JOIN holders b ON b.cusip = h.cusip AND b.period = p.prev_period
            JOIN filers_total ft ON ft.period = h.period
            JOIN filers_total fb ON fb.period = p.prev_period
            WHERE h.period = ? AND h.funds_holding >= ? AND b.funds_holding >= ? AND {metric} {sign} 0
            ORDER BY {metric} {order}, h.cusip
            LIMIT ?
            """,
            [period, minimum, minimum, limit],
        ).fetchall()
    ]


@pytest.mark.parametrize("by", ["tide", "count"])
def test_q2_2026_lists_render_and_match_plain_sql(client, con, by):
    response = client.get(f"/changes?period=2026-06-30&by={by}")
    assert response.status_code == 200
    lists = _lists(response.text)
    for most in ("added", "lost"):
        assert len(lists[most]) == 25
        assert [r["cusip"] for r in lists[most]] == _plain_sql_ranking(con, Q2_2026, 100, by, most, 25)


@pytest.mark.parametrize("minimum", [100, 500, 2000])
def test_no_stock_below_the_minimum_appears(client, con, minimum):
    lists = _lists(client.get(f"/changes?period=2026-06-30&min={minimum}&n=100").text)
    rows = lists["added"] + lists["lost"]
    assert rows
    for r in rows:
        assert r["funds"] >= minimum and r["funds_prev"] >= minimum, r
    for most in ("added", "lost"):
        assert [r["cusip"] for r in lists[most]] == _plain_sql_ranking(con, Q2_2026, minimum, "tide", most, 100)


def test_every_row_links_to_its_lookup_page(client):
    html = client.get("/changes").text
    for cusip in re.findall(r'href="/stock/([0-9A-Z]{9})"', html)[:5]:
        assert client.get(f"/stock/{cusip}").status_code == 200


def test_every_period_renders(client, con):
    for (period,) in con.execute("SELECT period FROM periods WHERE prev_period IS NOT NULL").fetchall():
        response = client.get(f"/changes?period={period.isoformat()}")
        assert response.status_code == 200
        assert f"positions {period:%b} {period.day}</option>" in response.text


def test_year_end_note_explains_the_jump(client):
    assert "Every Dec 31 the count jumps" in client.get("/changes?period=2025-12-31").text
    assert "Every Dec 31 the count jumps" not in client.get("/changes?period=2026-06-30").text


def test_a_cusip_change_is_not_a_mover(client):
    """Honeywell's old CUSIP lost 95% of its funds in Q2 2026 when it was replaced;
    only the stock, counted across both CUSIPs, may appear."""
    html = client.get("/changes?period=2026-06-30&n=100").text
    assert "/stock/438516106" not in html
