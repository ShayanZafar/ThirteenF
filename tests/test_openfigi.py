"""The OpenFIGI client and cache, against a fake OpenFIGI (no network, no real waiting)."""

import json
from contextlib import nullcontext

import duckdb
import httpx
import pytest

from thirteenf import health
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
    return {
        "figi": f"F-{ticker}-{exch}",
        "name": f"{ticker} INC",
        "ticker": ticker,
        "exchCode": exch,
        "compositeFIGI": f"C-{ticker}",
        "securityType": kind,
        "marketSector": "Equity",
        "shareClassFIGI": share_class or f"S-{ticker}",
        "securityType2": kind,
        "securityDescription": ticker,
    }


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


def _dropped(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("Connection reset by peer", request=request)


REFUSALS = {
    "429": lambda request: httpx.Response(429, headers={"ratelimit-reset": "3"}),
    "503": lambda request: httpx.Response(503, text="Service Unavailable"),
    "dropped": _dropped,
}


def fake_openfigi(requests_seen, fail_first=0, error_for=(), rejected=(), lopsided_with=(), refusal="429"):
    """A fake OpenFIGI; its first `fail_first` requests get `refusal` (one of REFUSALS)."""
    state = {"failures": fail_first}

    def handler(request: httpx.Request) -> httpx.Response:
        jobs = json.loads(request.content)
        requests_seen.append((request.headers.get("X-OPENFIGI-APIKEY"), jobs))
        if state["failures"]:
            state["failures"] -= 1
            return REFUSALS[refusal](request)
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
    rows = {
        r[0]: r
        for r in con.execute("SELECT cusip, found, ticker, security_type, id_type, exch_code FROM openfigi").fetchall()
    }
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


@pytest.mark.parametrize(
    "refusal, outcome, what",
    [("429", "throttled", "HTTP 429"), ("503", "failed", "HTTP 503"), ("dropped", "failed", "connection failed")],
)
def test_a_refusal_or_failure_is_not_waited_out(refusal, outcome, what):
    """The owner's rules (Oct 11, 2026): no sleeping on a 429, a 5xx or a dropped
    connection; the caller turns to the next source and asks OpenFIGI again next time."""
    seen, clock = [], FakeClock()
    client = openfigi.OpenFigiClient(
        "key", transport=fake_openfigi(seen, fail_first=1, refusal=refusal), sleep=clock.sleep, clock=clock.clock
    )
    job = {"idType": "ID_CUSIP", "idValue": "037833100", "exchCode": "US"}
    with pytest.raises(openfigi.OpenFigiUnavailable, match=what):
        client.map([job])
    assert len(seen) == 1 and clock.slept == []
    assert client.map([job])[0]["data"][0]["ticker"] == "AAPL"  # the next request asks again, at once
    assert len(seen) == 2 and clock.slept == []
    entry = health.load()["sources"]["openfigi"]
    assert (entry["ok"], entry[outcome]) == (1, 1) and entry["lastError"].startswith(what)


@pytest.mark.parametrize("refusal", list(REFUSALS))
def test_a_batch_openfigi_does_not_answer_goes_down_the_chain_at_once(con, refusal):
    """Its CUSIPs go to the fallback, nothing is cached for them, and the next batch asks OpenFIGI again."""
    seen, clock, handed = [], FakeClock(), []
    client = openfigi.OpenFigiClient(
        "key", transport=fake_openfigi(seen, fail_first=1, refusal=refusal), sleep=clock.sleep, clock=clock.clock
    )
    client.limits = openfigi.Limits(jobs_per_request=2, requests_per_window=25, window_seconds=6.0)
    counts = openfigi.update(lambda: nullcontext(con), client, log=lambda *_: None, fallback=handed.append)
    first = [job["idValue"] for job in seen[0][1]]
    assert handed[0] == sorted(first) and clock.slept == []
    assert len(seen) > 2 and all(len(jobs) <= 2 for _, jobs in seen)  # every later batch was asked
    cached = {r[0] for r in con.execute("SELECT cusip FROM openfigi").fetchall()}
    assert not cached & set(first)  # not an answer: asked again next run
    assert {"037833100", "464287200"} - set(first) <= cached
    assert counts["refused_batches"] == 1
    # The next run asks OpenFIGI about them again.
    seen.clear()
    openfigi.update(lambda: nullcontext(con), client, log=lambda *_: None, fallback=handed.append)
    assert set(first) <= {job["idValue"] for _, jobs in seen for job in jobs}


def test_openfigis_answer_replaces_a_provisional_ticker(con):
    con.execute(openfigi.CACHE_DDL)
    con.execute(
        """
        INSERT INTO ticker_fallbacks VALUES
            ('037833100', 'AAPL', 'sec-ftd', DATE '2026-09-15', NULL, TIMESTAMP '2026-10-01 00:00:00'),
            ('88579Y101', 'MMM', 'issuer-name', NULL, '3M CO', TIMESTAMP '2026-10-01 00:00:00'),
            ('17275R102', 'CSCO', 'sec-ftd', DATE '2026-09-15', NULL, TIMESTAMP '2026-10-01 00:00:00')
        """
    )
    seen, clock = [], FakeClock()
    transport = fake_openfigi(seen, error_for={"17275R102"})
    client = openfigi.OpenFigiClient("key", transport=transport, sleep=clock.sleep, clock=clock.clock)
    handed = []
    openfigi.update(lambda: nullcontext(con), client, log=lambda *_: None, fallback=handed.extend)
    left = dict(con.execute("SELECT cusip, ticker FROM ticker_fallbacks").fetchall())
    # Found by OpenFIGI, or known not to be there: OpenFIGI's answer stands. An error is
    # no answer, so that CUSIP keeps its provisional ticker and goes down the chain again.
    assert left == {"17275R102": "CSCO"}
    assert "17275R102" in handed and "037833100" not in handed


def test_text_with_quotes_is_stored_safely():
    c = duckdb.connect()
    c.execute(openfigi.CACHE_DDL)
    row = (
        "123456789",
        "ID_CUSIP",
        "123456789",
        True,
        "X",
        "O'NEIL'S; DROP TABLE x",
        "US",
        None,
        None,
        None,
        None,
        None,
        None,
        '{"a":"it\'s"}',
        openfigi.datetime(2026, 10, 2),
    )
    openfigi._store(c, [row])
    assert c.execute("SELECT name FROM openfigi").fetchone()[0] == "O'NEIL'S; DROP TABLE x"
