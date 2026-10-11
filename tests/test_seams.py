"""Where the steps meet: route to route, build to tickers, request to network.

These run on a small made-up data set (tests/minidata.py) or on no data at all,
so they never skip.
"""

import httpx
import minidata
import pytest
from conftest import QUIET, map_mini_tickers, openfigi_down
from fastapi.testclient import TestClient

import thirteenf.tickers
from thirteenf.db import connect
from thirteenf.ingest import openfigi
from thirteenf.web.app import app


def _kinds(cusip):
    with connect(read_only=True) as con:
        stock = con.execute("SELECT kind FROM stocks WHERE cusip = ?", [cusip]).fetchone()[0]
        periods = {r[0] for r in con.execute("SELECT kind FROM stock_periods WHERE cusip = ?", [cusip]).fetchall()}
    return stock, periods


def test_search_keeps_an_ampersand_in_the_query():
    response = TestClient(app).get("/search", params={"q": "AT&T"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/stock?q=AT%26T"


def test_the_made_up_data_builds_every_period(mini_db):
    with connect(read_only=True) as con:
        periods = [r[0].isoformat() for r in con.execute("SELECT period FROM periods ORDER BY 1").fetchall()]
        funds = con.execute(
            "SELECT funds_holding FROM stock_periods WHERE cusip = ? ORDER BY period", [minidata.QQQ]
        ).fetchall()
    assert periods == ["2024-06-30", "2024-09-30", "2024-12-31"]
    assert [f[0] for f in funds] == list(minidata.SECURITIES[minidata.QQQ][3])


def test_new_tickers_reach_the_kind_medians(mini_db, monkeypatch):
    """A ticker run can turn an 'other' into an ETF. stock_periods compares each
    stock with the median of its kind, so it has to follow."""
    assert _kinds(minidata.QQQ) == ("other", {"other"})

    map_mini_tickers(monkeypatch)

    assert _kinds(minidata.QQQ) == ("etf", {"etf"})
    with connect(read_only=True) as con:
        qqq_pct, etf_median = con.execute(
            "SELECT funds_pct, market_median_pct FROM stock_periods WHERE cusip = ? AND period = DATE '2024-12-31'",
            [minidata.QQQ],
        ).fetchone()
    assert etf_median == pytest.approx(qqq_pct)  # the only ETF is its own median


def test_a_dropped_connection_moves_on_at_once_and_the_next_request_asks_again():
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("[Errno -3] Temporary failure in name resolution", request=request)
        return httpx.Response(200, json=[{"warning": "No identifier found."}])

    slept = []
    client = openfigi.OpenFigiClient("key", transport=httpx.MockTransport(flaky), sleep=slept.append)
    with pytest.raises(openfigi.OpenFigiUnavailable, match="connection failed"):
        client.map([{"idType": "ID_CUSIP", "idValue": "037833100"}])
    assert client.map([{"idType": "ID_CUSIP", "idValue": "037833100"}]) == [{"warning": "No identifier found."}]
    assert calls["n"] == 2 and slept == []


def test_a_connection_that_stays_down_never_stops_the_run(mini_db, monkeypatch):
    """Every batch goes down the chain; the run finishes, and every CUSIP is asked again next time."""
    slept: list[float] = []
    handed: list[str] = []
    openfigi_down(monkeypatch, slept)

    class Recorder(thirteenf.tickers.TickerFallback):
        def __call__(self, cusips: list[str]) -> None:
            handed.extend(cusips)

    counts = thirteenf.tickers.update_tickers(log=QUIET, fallback=Recorder(connect, QUIET))
    assert sorted(handed) == sorted(minidata.SECURITIES) and slept == []
    assert counts["errors"] == len(minidata.SECURITIES) and counts["refused_batches"] == 1
    with connect() as con:
        assert sorted(openfigi.pending_cusips(con)) == sorted(minidata.SECURITIES)
