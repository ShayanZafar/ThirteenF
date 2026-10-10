"""Where the steps meet: route to route, build to tickers, request to network.

These run on a small made-up data set (tests/minidata.py) or on no data at all,
so they never skip.
"""

import json

import httpx
import minidata
import pytest
from fastapi.testclient import TestClient

import thirteenf.db
import thirteenf.tickers
from thirteenf.db import connect
from thirteenf.ingest import load, openfigi
from thirteenf.model import build
from thirteenf.web.app import app

QUIET = lambda *_: None


@pytest.fixture
def mini_db(tmp_path, monkeypatch):
    """The made-up data set, loaded and built, in a database of its own."""
    monkeypatch.setattr(thirteenf.db, "DB_PATH", tmp_path / "mini.duckdb")
    with connect() as con:
        load.ensure_load_log(con)
        for path in minidata.write_zips(tmp_path / "raw"):
            load.load_zip(con, path, log=QUIET, work_root=tmp_path / "work")
    build.build_all(log=QUIET)
    return tmp_path / "mini.duckdb"


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


def _fake_openfigi(request: httpx.Request) -> httpx.Response:
    out = []
    for job in json.loads(request.content):
        if job["idType"] != "ID_CUSIP" or job["idValue"] not in minidata.SECURITIES:
            out.append({"warning": "No identifier found."})
            continue
        etf = job["idValue"] == minidata.QQQ
        ticker = "QQQ" if etf else f"T{job['idValue'][:3]}"
        out.append({"data": [{"ticker": ticker, "exchCode": "US", "securityType": "ETP" if etf else "Common Stock"}]})
    return httpx.Response(200, json=out)


def test_new_tickers_reach_the_kind_medians(mini_db, monkeypatch):
    """A ticker run can turn an 'other' into an ETF. stock_periods compares each
    stock with the median of its kind, so it has to follow."""
    assert _kinds(minidata.QQQ) == ("other", {"other"})

    real_client = openfigi.OpenFigiClient
    monkeypatch.setattr(thirteenf.tickers, "openfigi_api_key", lambda: "test-key")
    monkeypatch.setattr(
        openfigi,
        "OpenFigiClient",
        lambda key: real_client(key, transport=httpx.MockTransport(_fake_openfigi), sleep=lambda _: None),
    )
    thirteenf.tickers.update_tickers(log=QUIET)

    assert _kinds(minidata.QQQ) == ("etf", {"etf"})
    with connect(read_only=True) as con:
        qqq_pct, etf_median = con.execute(
            "SELECT funds_pct, market_median_pct FROM stock_periods WHERE cusip = ? AND period = DATE '2024-12-31'",
            [minidata.QQQ],
        ).fetchone()
    assert etf_median == pytest.approx(qqq_pct)  # the only ETF is its own median


def test_a_dropped_connection_is_retried():
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise httpx.ConnectError("[Errno -3] Temporary failure in name resolution", request=request)
        return httpx.Response(200, json=[{"warning": "No identifier found."}])

    slept = []
    client = openfigi.OpenFigiClient("key", transport=httpx.MockTransport(flaky), sleep=slept.append)
    assert client.map([{"idType": "ID_CUSIP", "idValue": "037833100"}]) == [{"warning": "No identifier found."}]
    assert calls["n"] == 3 and len(slept) == 2


def test_a_connection_that_stays_down_still_fails():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = openfigi.OpenFigiClient("key", transport=httpx.MockTransport(down), sleep=lambda _: None)
    with pytest.raises(httpx.ConnectError):
        client.map([{"idType": "ID_CUSIP", "idValue": "037833100"}])
