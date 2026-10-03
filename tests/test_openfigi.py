"""The OpenFIGI client and cache, against a fake OpenFIGI (no network)."""

import json
from contextlib import nullcontext

import duckdb
import httpx
import pytest

from thirteenf.ingest import openfigi


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def _listing(ticker, exch="US", kind="Common Stock", share_class=None):
    return {"figi": f"F-{ticker}-{exch}", "name": f"{ticker} INC", "ticker": ticker, "exchCode": exch,
            "compositeFIGI": f"C-{ticker}", "securityType": kind, "marketSector": "Equity",
            "shareClassFIGI": share_class or f"S-{ticker}", "securityType2": kind, "securityDescription": ticker}


KNOWN = {
    ("ID_CUSIP", "037833100"): [_listing("AAPL", "UW"), _listing("AAPL")],
    ("ID_CUSIP", "464287200"): [_listing("IVV", kind="ETP")],
    ("ID_BB_GLOBAL", "BBG000000001"): [_listing("OLDCO")],
    # Found only by its CINS code.
    ("ID_CINS", "G29183103"): [_listing("ETN")],
    # Listed only abroad under its CUSIP; its share class leads to the US listing.
    ("ID_CUSIP", "682680103"): [_listing("OKEEUR", "ER", share_class="S-OKE")],
    ("ID_BB_GLOBAL_SHARE_CLASS_LEVEL", "S-OKE"): [_listing("OKE")],
}


def fake_openfigi(requests_seen, fail_first=0, error_for=(), rejected=(), lopsided_with=()):
    state = {"failures": fail_first}

    def handler(request: httpx.Request) -> httpx.Response:
        jobs = json.loads(request.content)
        requests_seen.append((request.headers.get("X-OPENFIGI-APIKEY"), jobs))
        if state["failures"]:
            state["failures"] -= 1
            return httpx.Response(429, headers={"ratelimit-reset": "3"})
        if len(jobs) > 1 and any(job["idValue"] in lopsided_with for job in jobs):
            return httpx.Response(200, json=[{"error": "Something went wrong"}])
        out = []
        for job in jobs:
            if job["idValue"] in error_for:
                out.append({"error": "Internal error, try again."})
            elif job["idValue"] in rejected:
                out.append({"error": openfigi.REJECTED})
            else:
                listings = KNOWN.get((job["idType"], job["idValue"]), [])
                if job.get("exchCode"):
                    listings = [d for d in listings if d["exchCode"] == job["exchCode"]]
                out.append({"data": listings} if listings else {"warning": "No identifier found."})
        return httpx.Response(200, json=out)

    return httpx.MockTransport(handler)


# Real-format CUSIPs (valid check digits) for the fake's unknowns.
UNKNOWN, FAILING, REJECTED_BY_FIGI = "88579Y101", "17275R102", "92826C839"


@pytest.fixture()
def con():
    c = duckdb.connect()
    c.execute(
        f"""
        CREATE TABLE securities AS SELECT * FROM (VALUES
            ('037833100', NULL, DATE '2026-06-30'),
            ('464287200', NULL, DATE '2026-06-30'),
            ('000000001', 'BBG000000001', DATE '2025-03-31'),
            ('{UNKNOWN}', NULL, DATE '2026-06-30'),
            ('{FAILING}', NULL, DATE '2026-06-30'),
            ('{REJECTED_BY_FIGI}', NULL, DATE '2026-06-30'),
            ('G29183103', NULL, DATE '2026-06-30'),
            ('682680103', NULL, DATE '2026-06-30')
        ) t(cusip, figi, latest_period)
        """
    )
    return c


def test_maps_cusips_then_filers_figis_and_caches_answers(con):
    seen, clock = [], FakeClock()
    transport = fake_openfigi(seen, error_for={FAILING}, rejected={REJECTED_BY_FIGI}, lopsided_with={UNKNOWN})
    client = openfigi.OpenFigiClient("key", transport=transport, sleep=clock.sleep, clock=clock.clock)
    counts = openfigi.update(lambda: nullcontext(con), client, log=lambda *_: None)
    rows = {r[0]: r for r in con.execute("SELECT cusip, found, ticker, security_type, id_type, exch_code FROM openfigi").fetchall()}
    assert rows["037833100"][1:4] == (True, "AAPL", "Common Stock")
    assert rows["037833100"][5] == "US"  # the US composite listing, not the first one
    assert rows["464287200"][3] == "ETP"
    # A wrong check digit is not sent, but the filers' FIGI still finds it.
    assert rows["000000001"][1:3] == (True, "OLDCO") and rows["000000001"][4] == "ID_BB_GLOBAL"
    assert all(job["idValue"] != "000000001" for _, jobs in seen for job in jobs if job["idType"] == "ID_CUSIP")
    assert rows[UNKNOWN][1] is False  # found after its batch was split
    assert rows[REJECTED_BY_FIGI][1] is False  # rejected: a final answer, cached
    assert FAILING not in rows  # a passing error is not cached
    assert rows["G29183103"][1:3] == (True, "ETN") and rows["G29183103"][4] == "ID_CINS"
    assert rows["682680103"][1:3] == (True, "OKE") and rows["682680103"][4] == "ID_BB_GLOBAL_SHARE_CLASS_LEVEL"
    assert counts["errors"] >= 1
    assert all(key == "key" for key, _ in seen)
    # The raw answer is kept.
    response = con.execute("SELECT response FROM openfigi WHERE cusip = '037833100'").fetchone()[0]
    assert json.loads(response)["data"][0]["ticker"] == "AAPL"

    # A second run asks only about what is still unknown: the CUSIP that errored.
    seen.clear()
    openfigi.update(lambda: nullcontext(con), client, log=lambda *_: None)
    assert {job["idValue"] for _, jobs in seen for job in jobs} == {FAILING}


def test_the_us_composite_listing_is_chosen():
    listings = [_listing("AAPL", "UW"), _listing("AAPL", "US"), _listing("AAPL", "UN")]
    assert openfigi.choose(listings)["exchCode"] == "US"
    assert openfigi.choose([_listing("OKEEUR", "ER")])["exchCode"] == "ER"


def test_check_digits():
    for good in ("037833100", "82509L107", "02079K305", "084670702", "G2004J103"):
        assert openfigi.valid_cusip(good), good
    for bad in ("000000001", "037833101", "82509L10X", "12345", "ABCDEFGHI"):
        assert not openfigi.valid_cusip(bad), bad


def test_batches_and_paces_requests_to_the_limits():
    seen, clock = [], FakeClock()
    client = openfigi.OpenFigiClient("", transport=fake_openfigi(seen), sleep=clock.sleep, clock=clock.clock)
    assert client.limits == openfigi.WITHOUT_KEY
    with pytest.raises(ValueError):
        client.map([{"idType": "ID_CUSIP", "idValue": str(i)} for i in range(11)])
    for _ in range(26):
        client.map([{"idType": "ID_CUSIP", "idValue": "1"}])
    # The 26th request waits for the first to leave the 60-second window.
    assert len(clock.slept) == 1 and 59 < clock.slept[0] < 61
    assert seen[0][0] is None  # no key header without a key


def test_waits_and_retries_when_told_to_slow_down():
    seen, clock = [], FakeClock()
    client = openfigi.OpenFigiClient("key", transport=fake_openfigi(seen, fail_first=2), sleep=clock.sleep, clock=clock.clock)
    result = client.map([{"idType": "ID_CUSIP", "idValue": "037833100", "exchCode": "US"}])
    assert result[0]["data"][0]["ticker"] == "AAPL"
    assert len(seen) == 3 and clock.slept[:2] == [3.0, 3.0]


def test_text_with_quotes_is_stored_safely():
    c = duckdb.connect()
    c.execute(openfigi.CACHE_DDL)
    row = ("123456789", "ID_CUSIP", "123456789", True, "X", "O'NEIL'S; DROP TABLE x", "US", None, None,
           None, None, None, None, '{"a":"it\'s"}', openfigi.datetime(2026, 10, 2))
    openfigi._store(c, [row])
    assert c.execute("SELECT name FROM openfigi").fetchone()[0] == "O'NEIL'S; DROP TABLE x"
