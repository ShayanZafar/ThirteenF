"""Daily prices and volume: the Stooq and Tiingo clients against fakes, the chain when one
refuses, the "priced in" reading on rows written by hand, the Accumulate page on the made-up
data with made-up prices, and in a browser. No test touches a live source or really waits."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import duckdb
import httpx
import pytest
from conftest import QUIET
from fastapi.testclient import TestClient
from model_rows import PERIOD, cash_flow, model, prices, stock, stock_period
from playwright.sync_api import Page, expect
from test_accumulate import accumulate_db  # noqa: F401  (the fixture: made-up financials and tickers)

import thirteenf.prices
from thirteenf import health
from thirteenf.db import connect
from thirteenf.ingest import prices as ingest
from thirteenf.ingest.prices import Stooq, Tiingo
from thirteenf.web import data
from thirteenf.web.app import app

AAPL, MSFT, NVDA, AMZN = "037833100", "594918104", "67066G104", "023135106"
FIRST_DAY, LAST_DAY = date(2024, 6, 3), date(2025, 1, 15)
QUARTER_START = date(2024, 9, 30)  # the Q4 2024 list compares against Q3's end
NOW = datetime(2025, 1, 16, 12, tzinfo=UTC)

# --- Fakes -----------------------------------------------------------------------------


def weekdays(first: date = FIRST_DAY, last: date = LAST_DAY) -> list[date]:
    day, out = first, []
    while day <= last:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def ramp(start: float, end: float) -> Callable[[date], float]:
    """A price that moves in a straight line from `start` on the first day to `end` on the last."""
    span = (LAST_DAY - FIRST_DAY).days
    return lambda d: round(start + (end - start) * (d - FIRST_DAY).days / span, 4)


def stooq_csv(price: Callable[[date], float]) -> str:
    rows = [f"{d.isoformat()},{price(d)},{price(d)},{price(d)},{price(d)},1000000" for d in weekdays()]
    return "\n".join([Stooq.HEADER, *rows]) + "\n"


def tiingo_json(price: Callable[[date], float]) -> str:
    return json.dumps(
        [
            {
                "date": f"{d.isoformat()}T00:00:00.000Z",
                "close": price(d),
                "adjOpen": price(d),
                "adjHigh": price(d),
                "adjLow": price(d),
                "adjClose": price(d),
                "adjVolume": 2000000,
            }
            for d in weekdays()
        ]
    )


class FakeSources:
    """Stooq and Tiingo behind mock transports. `series` maps a symbol to its price; a symbol
    not in it gets "No data" from Stooq and a 404 from Tiingo. Stooq answers its limit message
    after `stooq_limit` requests, if given."""

    def __init__(self, series: dict[str, Callable[[date], float]], stooq_limit: int | None = None):
        self.series, self.stooq_limit = series, stooq_limit
        self.stooq_asked: list[str] = []
        self.tiingo_asked: list[str] = []

    def _stooq(self, request: httpx.Request) -> httpx.Response:
        symbol = request.url.params["s"]
        self.stooq_asked.append(symbol)
        if self.stooq_limit is not None and len(self.stooq_asked) > self.stooq_limit:
            return httpx.Response(200, text="Przekroczony dzienny limit wywolan")
        key = symbol.removesuffix(".us").upper()
        if key not in self.series:
            return httpx.Response(200, text="No data")
        return httpx.Response(200, text=stooq_csv(self.series[key]))

    def _tiingo(self, request: httpx.Request) -> httpx.Response:
        symbol = request.url.path.split("/")[3]
        self.tiingo_asked.append(symbol)
        if symbol not in self.series:
            return httpx.Response(404, text="Not found.")
        return httpx.Response(200, text=tiingo_json(self.series[symbol]))

    def stooq(self, key: str = "stooq-key") -> Stooq:
        return Stooq(key, transport=httpx.MockTransport(self._stooq))

    def tiingo(self, key: str = "tiingo-key", clock=lambda: 1000.0) -> Tiingo:
        return Tiingo(key, transport=httpx.MockTransport(self._tiingo), clock=clock)


MARKET = ramp(450, 600)  # the market: up about 13% from the quarter's start to the last day


def _events() -> list[tuple[str, str]]:
    return [(e["source"], e["outcome"]) for e in health.load_events()]


# --- Unit: the clients and the chain ------------------------------------------------------


def test_symbols_are_spelled_the_way_each_source_wants():
    assert ingest.symbol_key("BRK/B") == "BRK-B"
    assert ingest.symbol_key(" brk.b ") == "BRK-B"
    seen: list[httpx.Request] = []
    stooq = Stooq(
        "k1", transport=httpx.MockTransport(lambda r: (seen.append(r), httpx.Response(200, text="No data"))[1])
    )
    tiingo = Tiingo("k2", transport=httpx.MockTransport(lambda r: (seen.append(r), httpx.Response(404))[1]))
    assert stooq.fetch("BRK-B", date(2026, 10, 26)) is None
    assert tiingo.fetch("BRK-B", date(2026, 10, 26)) is None
    assert seen[0].url.params["s"] == "brk-b.us" and seen[0].url.params["d1"] == "20231026"
    assert seen[0].url.params["apikey"] == "k1"
    assert seen[1].url.path == "/tiingo/daily/BRK-B/prices" and seen[1].url.params["startDate"] == "2023-10-26"
    assert seen[1].headers["Authorization"] == "Token k2"
    assert _events() == [("stooq", "ok"), ("tiingo", "ok")]  # "no data" is an answer


def test_stooqs_limit_message_moves_the_rest_of_the_run_to_tiingo(tmp_path):
    fakes = FakeSources({"AAA": ramp(10, 20), "BBB": ramp(10, 10), "CCC": ramp(10, 30)}, stooq_limit=1)
    db = duckdb.connect()
    counts = ingest.update(
        lambda: _keep_open(db),
        [fakes.stooq(), fakes.tiingo()],
        ["AAA", "BBB", "CCC"],
        log=QUIET,
        now=NOW,
        folder=tmp_path,
    )
    assert counts == {"wanted": 3, "due": 3, "fetched": 3, "no_data": 0, "left": 0}
    assert fakes.stooq_asked == ["aaa.us", "bbb.us"]  # the second was refused: Stooq is not asked again
    assert fakes.tiingo_asked == ["BBB", "CCC"]
    assert (tmp_path / "stooq" / "AAA.csv").read_text().startswith(Stooq.HEADER)
    assert (tmp_path / "tiingo" / "BBB.json").exists() and not (tmp_path / "stooq" / "BBB.csv").exists()
    sources = dict(db.execute("SELECT symbol, source FROM price_fetches ORDER BY symbol").fetchall())
    assert sources == {"AAA": "stooq", "BBB": "tiingo", "CCC": "tiingo"}
    rows = db.execute("SELECT symbol, count(*), max(close) FROM raw_prices GROUP BY symbol ORDER BY symbol").fetchall()
    assert rows == [("AAA", len(weekdays()), 20.0), ("BBB", len(weekdays()), 10.0), ("CCC", len(weekdays()), 30.0)]
    assert _events() == [("stooq", "ok"), ("stooq", "throttled"), ("tiingo", "ok"), ("tiingo", "ok")]


def test_a_source_with_no_data_leaves_the_symbol_to_the_next_and_a_symbol_fetched_today_is_not_asked_again(tmp_path):
    fakes = FakeSources({"AAA": ramp(10, 20)})
    db = duckdb.connect()
    chain = [fakes.stooq(), fakes.tiingo()]
    counts = ingest.update(lambda: _keep_open(db), chain, ["AAA", "ZZZ"], log=QUIET, now=NOW, folder=tmp_path)
    assert counts["fetched"] == 1 and counts["no_data"] == 1
    assert fakes.stooq_asked == ["aaa.us", "zzz.us"] and fakes.tiingo_asked == ["ZZZ"]  # both asked, neither knew
    again = ingest.update(lambda: _keep_open(db), chain, ["AAA", "ZZZ"], log=QUIET, now=NOW, folder=tmp_path)
    assert again == {"wanted": 2, "due": 0, "fetched": 0, "no_data": 0, "left": 0}
    later = ingest.update(
        lambda: _keep_open(db), chain, ["AAA", "ZZZ"], log=QUIET, now=NOW + ingest.REFRESH_AFTER, folder=tmp_path
    )
    assert later["due"] == 2


def test_tiingo_is_asked_about_at_most_fifty_symbols_an_hour_and_never_waited_for(tmp_path):
    fakes = FakeSources({f"S{n:02d}": ramp(1, 2) for n in range(60)})
    clock = {"now": 1000.0}
    db = duckdb.connect()
    symbols = sorted(fakes.series)
    counts = ingest.update(
        lambda: _keep_open(db), [fakes.tiingo(clock=lambda: clock["now"])], symbols, log=QUIET, now=NOW, folder=tmp_path
    )
    assert counts["fetched"] == Tiingo.SYMBOLS_PER_HOUR and counts["left"] == 10
    assert len(fakes.tiingo_asked) == Tiingo.SYMBOLS_PER_HOUR


def test_a_failing_source_is_left_at_once_and_what_was_fetched_stays(tmp_path):
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection reset by peer", request=request)

    db = duckdb.connect()
    stooq = Stooq("k", transport=httpx.MockTransport(down))
    counts = ingest.update(lambda: _keep_open(db), [stooq], ["AAA", "BBB"], log=QUIET, now=NOW, folder=tmp_path)
    assert counts == {"wanted": 2, "due": 2, "fetched": 0, "no_data": 0, "left": 2}
    assert _events() == [("stooq", "failed")]
    html = Stooq("k", transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>Sign in</html>")))
    with pytest.raises(ingest.PriceSourceDown):
        html.fetch("AAA", NOW.date())


class _keep_open:
    """A connection used as a context manager that stays open, for the in-memory tests."""

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self.con = con

    def __enter__(self) -> duckdb.DuckDBPyConnection:
        return self.con

    def __exit__(self, *exc) -> None:
        pass


# --- Unit: the reading, on rows written by hand ---------------------------------------------


def test_a_pick_is_lagging_in_line_or_ahead_of_the_market():
    assert data.priced_in(-data.PRICE_LAG_PTS) == "lagging"
    assert data.priced_in(-4.9) == "in line"
    assert data.priced_in(0.0) == "in line"
    assert data.priced_in(data.PRICE_LAG_PTS) == "ahead"
    assert data.priced_in(None) is None


LAGGING, AHEAD, UNPRICED = "L00000001", "A00000001", "U00000001"


def _list_db():
    stocks, rows, flows = [], [], []
    for cusip in (LAGGING, AHEAD, UNPRICED):
        stocks.append(stock(cusip, f"Company {cusip[0]}"))
        rows.append(stock_period(cusip, 150, 140, filers_pct=0.02, streak=2, net_flow=2e7, value=1e9))
        flows.append(cash_flow(cusip, 6e9, 7e9, diluted_shares=1e9))
    # The market is up 10% since the quarter's start; one pick is flat, one is up 30%, one has no prices.
    return model(stocks, rows, flows, [prices(LAGGING, 0.0, 0.10), prices(AHEAD, 0.30, 0.10)])


def test_the_list_reads_each_picks_price_against_the_market_and_ranks_the_laggards_first():
    con = _list_db()
    by_yield = {r["cusip"]: r for r in data.accumulate(con, PERIOD, 100, 0.05, 2)}
    assert by_yield[LAGGING]["priced"] == "lagging" and by_yield[LAGGING]["vs_market_pts"] == pytest.approx(-10)
    assert by_yield[AHEAD]["priced"] == "ahead" and by_yield[AHEAD]["since_start_pct"] == pytest.approx(0.30)
    assert by_yield[LAGGING]["flow_share"] == pytest.approx(0.02)  # $20M bought of $1B traded
    assert by_yield[UNPRICED]["priced"] is None and by_yield[UNPRICED]["flow_share"] is None
    ranked = [r["cusip"] for r in data.accumulate(con, PERIOD, 100, 0.05, 2, by="price")]
    assert ranked == [LAGGING, AHEAD, UNPRICED]  # a stock without prices last


def test_a_database_built_before_prices_still_lists_stocks():
    con = model(
        [stock(AHEAD, "Company A")],
        [stock_period(AHEAD, 150, 140, filers_pct=0.02, streak=2, net_flow=1e6)],
        [cash_flow(AHEAD, 6e9, 7e9, diluted_shares=1e9)],
    )
    rows = data.accumulate(con, PERIOD, 100, 0.05, 2, by="price")
    assert [r["cusip"] for r in rows] == [AHEAD] and rows[0]["since_start_pct"] is None
    assert data.prices_status(con) is None


# --- Integration: the made-up data with made-up prices ---------------------------------------


@pytest.fixture
def priced_db(accumulate_db, tmp_path, monkeypatch):  # noqa: F811
    """The made-up data with financials and tickers, plus daily prices from a fake Stooq:
    MSFT (T594) flat while the market rises, AMZN (T023) up about 25%, SPY the market. Returns the fakes."""
    accumulate_db()
    fakes = FakeSources({"SPY": MARKET, "T594": ramp(400, 400), "T023": ramp(150, 260), "T037": ramp(200, 220)})
    monkeypatch.setattr(ingest, "PRICES_DIR", tmp_path / "raw" / "prices")
    thirteenf.prices.update_prices(log=QUIET, chain=[fakes.stooq()], now=NOW)
    return fakes


def _expected(price: Callable[[date], float]) -> float:
    return price(LAST_DAY) / price(QUARTER_START) - 1


def test_prices_are_fetched_for_the_market_the_watchlist_and_the_candidates(priced_db):
    asked = {s.removesuffix(".us").upper() for s in priced_db.stooq_asked}
    assert "SPY" in asked and {"T594", "T023"} <= asked  # the market and the picks with streak 1
    assert "T037" in asked  # Apple: on the example watchlist, though its funds are flat
    with connect(read_only=True) as con:
        rows = {
            r[0]: r[1:]
            for r in con.execute(
                "SELECT cusip, since_start_pct, vs_market_pts, price_source FROM stock_prices WHERE period = ?",
                [PERIOD],
            ).fetchall()
        }
    assert rows[MSFT][0] == pytest.approx(0.0) and rows[MSFT][2] == "stooq"
    assert rows[MSFT][1] == pytest.approx(-100 * _expected(MARKET))
    assert rows[AMZN][1] == pytest.approx(100 * (_expected(ramp(150, 260)) - _expected(MARKET)))
    assert NVDA not in rows  # no prices were fetched for it


def test_the_page_says_whether_each_pick_has_priced_the_flow_in(priced_db):
    html = TestClient(app).get("/accumulate", params={"streak": 1}).text
    assert "Price since Sep 30" in html
    assert "Lagging the market" in html and "Ahead of the market" in html
    assert "Prices</b><i>·</i>Stooq, through Jan 15, 2025" in html
    assert "of value traded" in html
    ranked = re.findall(
        r'href="/stock/([0-9A-Z]{9})"', html.split("Stocks to accumulate", 1)[1].split("</table>", 1)[0]
    )
    assert ranked == [AMZN, MSFT]  # by yield
    lagging_first = TestClient(app).get("/accumulate", params={"streak": 1, "by": "price"}).text
    ranked = re.findall(
        r'href="/stock/([0-9A-Z]{9})"', lagging_first.split("Stocks to accumulate", 1)[1].split("</table>", 1)[0]
    )
    assert ranked == [MSFT, AMZN]
    stock_page = TestClient(app).get(f"/stock/{MSFT}").text
    assert "Price since Sep 30" in stock_page and "Lagging the market" in stock_page


def test_without_a_key_nothing_is_fetched_and_the_pages_still_work(accumulate_db, monkeypatch):  # noqa: F811
    accumulate_db()
    for name in ("stooq_api_key", "tiingo_api_key"):
        monkeypatch.setattr(thirteenf.prices, name, lambda: "")
    said: list[str] = []
    assert thirteenf.prices.update_prices(log=said.append) is None
    assert said and "Stooq" in said[0]
    html = TestClient(app).get("/accumulate").text
    assert "Quarter, from 13F prices" in html and "Prices</b>" not in html


# --- A browser --------------------------------------------------------------------------------


@pytest.mark.ui
def test_a_person_sees_whether_a_pick_is_already_priced_in(priced_db, page: Page):
    page.goto("/accumulate?streak=1")
    table = page.locator("section").filter(has=page.get_by_role("heading", name=re.compile("^Stocks to accumulate")))
    expect(table.get_by_role("columnheader", name="Price since Sep 30")).to_be_visible()
    expect(table.locator("tbody tr").filter(has_text="Microsoft")).to_contain_text("Lagging the market")
    expect(table.locator("tbody tr").filter(has_text="Amazon")).to_contain_text("Ahead of the market")
    expect(page.locator(".app-stamps .tf-stamp").filter(has_text="Prices")).to_have_text(
        "Prices·Stooq, through Jan 15, 2025"
    )
    page.get_by_role("group", name="Rank by").get_by_role("link", name="Price lagging").click()
    expect(page).to_have_url(re.compile(r"by=price"))
    hrefs = table.locator("tbody a[href^='/stock/']").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert hrefs == [f"/stock/{MSFT}", f"/stock/{AMZN}"]
    table.get_by_role("link").filter(has_text=re.compile("Microsoft", re.I)).first.click()
    expect(page.locator(".tf-kf").filter(has_text="Price since Sep 30")).to_contain_text("Lagging the market")
