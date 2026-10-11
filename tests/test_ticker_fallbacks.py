"""The ticker chain after OpenFIGI: the SEC's fails-to-deliver data, then an issuer-name match.

Against a fake OpenFIGI, a fake SEC and made-up files (no network, no real waiting):
which source answers, what the cache records, what the stock page says, how a later
OpenFIGI answer replaces a provisional ticker, and what the source health file says."""

import sys
from contextlib import nullcontext
from datetime import date

import duckdb
import httpx
import minidata
import pytest
from conftest import QUIET, FakeFtdSec, ftd_zip_bytes, map_mini_tickers, openfigi_down, write_ftd_zip
from fastapi.testclient import TestClient

import thirteenf.tickers
from thirteenf import health
from thirteenf.db import connect
from thirteenf.ingest import ftd, issuer_names, openfigi, xbrl
from thirteenf.tickers import TickerFallback
from thirteenf.web.app import app

AAPL, MSFT, NVDA, AMZN, QQQ = "037833100", "594918104", "67066G104", "023135106", minidata.QQQ
GOOGL, GOOG = "02079K305", "02079K107"
BLOCK_PAGE = "<html><h1>Request Rate Threshold Exceeded</h1></html>"


@pytest.fixture(autouse=True)
def setting_up(monkeypatch, tmp_path):
    monkeypatch.setenv("SEC_USER_AGENT", "ThirteenF tests@example.com")
    monkeypatch.setattr(ftd, "FTD_DIR", tmp_path / "ftd")


def with_check_digit(first8: str) -> str:
    return next(first8 + d for d in "0123456789" if openfigi.valid_cusip(first8 + d))


SOFI, SOFI_WARRANT = with_check_digit("83406F10"), with_check_digit("83406F11")


# --- The issuer-name match ---------------------------------------------------


@pytest.mark.parametrize(
    "filed, sec_title",
    [
        ("APPLE INC", "Apple Inc."),
        ("NVIDIA CORPORATION", "NVIDIA CORP"),
        ("BERKSHIRE HATHAWAY INC DEL CL B", "BERKSHIRE HATHAWAY INC"),
        ("AT&T INC", "AT&T INC."),
        ("US BANCORP DEL", "U.S. BANCORP /DE/"),
        ("TRADE DESK INC COM CL A", "The Trade Desk, Inc."),
        ("ALPHABET INC CAP STK CL A", "Alphabet Inc."),
        ("MCDONALDS CORP", "McDonald's Corp"),
        ("PROCTER AND GAMBLE CO", "PROCTER & GAMBLE Co"),
        ("META PLATFORMS INC CL A", "Meta Platforms, Inc."),
        ("ASML HOLDING N V", "ASML HOLDING N.V."),
    ],
)
def test_names_written_differently_normalise_alike(filed, sec_title):
    assert issuer_names.normalize(filed) == issuer_names.normalize(sec_title) != ""


@pytest.mark.parametrize(
    "one, other",
    [
        ("CISCO SYS INC", "Cisco Systems, Inc."),  # abbreviations are not guessed
        ("ARES CAP CORP", "ARES CORP"),  # CAP goes only with STK
        ("NEW YORK TIMES CO", "YORK TIMES CO"),  # NEW goes only at the end
        ("BANK OF AMERICA CORP", "AMERICA CORP"),
    ],
)
def test_different_names_stay_different(one, other):
    assert issuer_names.normalize(one) != issuer_names.normalize(other)


def test_what_a_normalised_name_looks_like():
    assert issuer_names.normalize("Apple Inc.") == "APPLE"
    assert issuer_names.normalize("U.S. Bancorp") == "USBANCORP"
    assert issuer_names.normalize("The Coca-Cola Company") == "COCACOLA"
    assert issuer_names.normalize("CO") == "" and issuer_names.normalize(None) == ""


@pytest.fixture
def db():
    """A database with the 13F names (securities) and the SEC's ticker list (raw_sec_tickers)."""
    con = duckdb.connect()
    con.execute(
        f"""
        CREATE TABLE securities AS SELECT * FROM (VALUES
            ('{AAPL}', '{AAPL}', 'APPLE INC'),
            ('{NVDA}', '{NVDA}', 'NVIDIA CORPORATION'),
            ('{MSFT}', '{MSFT}', 'MICROSOFT CORP'),
            ('594918105', '594918105', 'MICROSOFT CORP'),
            ('{GOOGL}', '{GOOGL}', 'ALPHABET INC'),
            ('{GOOG}', '{GOOG}', 'ALPHABET INC'),
            ('{SOFI}', '{SOFI}', 'SOFI TECHNOLOGIES INC'),
            ('{SOFI_WARRANT}', '{SOFI_WARRANT}', 'SOFI TECHNOLOGIES INC')
        ) t(cusip, stock, name_filed)
        """
    )
    con.execute(xbrl.RAW_DDL)
    con.execute(
        """
        INSERT INTO raw_sec_tickers VALUES
            (320193, 'AAPL', 'Apple Inc.'), (1045810, 'NVDA', 'NVIDIA CORP'), (789019, 'MSFT', 'MICROSOFT CORP'),
            (1652044, 'GOOGL', 'Alphabet Inc.'), (1652044, 'GOOG', 'Alphabet Inc.'),
            (1818874, 'SOFI', 'SoFi Technologies, Inc.')
        """
    )
    con.execute(openfigi.CACHE_DDL)
    return con


def test_a_name_counts_only_for_exactly_one_ticker_and_one_stock(db):
    names = issuer_names.NameMatch.from_db(db)
    assert names.ticker(AAPL) == ("AAPL", "Apple Inc.")
    assert names.ticker(NVDA) == ("NVDA", "NVIDIA CORP")
    assert names.ticker(GOOGL) is None  # two tickers carry the name (and two stocks)
    assert names.ticker(SOFI) is None and names.ticker(SOFI_WARRANT) is None  # the shares and the warrants
    assert names.ticker(MSFT) == ("MSFT", "MICROSOFT CORP")  # a filer's typo (594918105) does not make it ambiguous
    assert names.ticker("594918105") is None  # nor is the typo matched itself
    assert names.ticker("999999999") is None


def test_without_the_tables_nothing_matches():
    assert issuer_names.NameMatch.from_db(duckdb.connect()).ticker(AAPL) is None


# --- The chain ---------------------------------------------------------------


def _chain(db, fake, log=QUIET) -> TickerFallback:
    return TickerFallback(lambda: nullcontext(db), log=log, make_client=fake.client)


def _fallbacks(db) -> dict:
    rows = db.execute("SELECT cusip, ticker, source, as_of, detail FROM ticker_fallbacks").fetchall()
    return {r[0]: r[1:] for r in rows}


def test_the_fails_to_deliver_data_answers_first_then_the_issuer_name(db):
    name = "cnsfails202609a.zip"
    fake = FakeFtdSec({name: ftd_zip_bytes(name, [("20260915", AAPL, "AAPL", "10", "APPLE INC", "1")])})
    fallback = _chain(db, fake)
    fallback([AAPL, NVDA, GOOGL])
    assert _fallbacks(db) == {
        AAPL: ("AAPL", "sec-ftd", date(2026, 9, 15), None),
        NVDA: ("NVDA", "issuer-name", None, "NVIDIA CORP"),
    }
    # The next failed batch of the run uses what is loaded: the SEC is asked once a run.
    fallback([MSFT])
    assert fake.seen == ["fails-deliver-data", name]
    assert fallback.counts == {"asked": 4, "sec-ftd": 1, "issuer-name": 2}
    assert fallback.summary() == (
        "  OpenFIGI did not answer for 4 CUSIPs. Their tickers for now: 1 from the SEC's fails-to-deliver data, "
        "2 matched by issuer name (unverified), 1 none. The next run asks OpenFIGI again."
    )


def test_a_blocked_sec_leaves_the_issuer_name_match_at_once(db):
    fake = FakeFtdSec({}, refuse=lambda: httpx.Response(403, text=BLOCK_PAGE))
    logged: list[str] = []
    _chain(db, fake, logged.append)([AAPL, NVDA])
    assert fake.seen == ["fails-deliver-data"] and fake.slept == []
    assert {c: row[1] for c, row in _fallbacks(db).items()} == {AAPL: "issuer-name", NVDA: "issuer-name"}
    assert (
        "    The SEC paused requests from this computer (HTTP 403); using the files already downloaded, "
        "then the issuer-name match"
    ) in logged
    assert health.load()["sources"]["sec-ftd"]["throttled"] == 1


def test_the_files_already_here_answer_when_the_sec_does_not(db, tmp_path):
    write_ftd_zip(tmp_path / "ftd", "cnsfails202608b.zip", [("20260828", AAPL, "AAPL", "10", "APPLE INC", "1")])
    _chain(db, FakeFtdSec({}, refuse=httpx.ConnectError("Connection reset by peer")))([AAPL])
    assert _fallbacks(db) == {AAPL: ("AAPL", "sec-ftd", date(2026, 8, 28), None)}


def test_without_sec_user_agent_the_files_already_here_still_answer(db, tmp_path, monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT")
    write_ftd_zip(tmp_path / "ftd", "cnsfails202608b.zip", [("20260828", AAPL, "AAPL", "10", "APPLE INC", "1")])
    logged: list[str] = []
    TickerFallback(lambda: nullcontext(db), log=logged.append)([AAPL, NVDA])
    assert {c: row[1] for c, row in _fallbacks(db).items()} == {AAPL: "sec-ftd", NVDA: "issuer-name"}
    assert any("SEC_USER_AGENT is not set" in line for line in logged)


def test_a_later_fallback_answer_replaces_an_earlier_one(db):
    _chain(db, FakeFtdSec({}, refuse=lambda: httpx.Response(503)))([AAPL])
    assert _fallbacks(db)[AAPL][1] == "issuer-name"
    name = "cnsfails202609a.zip"
    files = {name: ftd_zip_bytes(name, [("20260915", AAPL, "AAPL", "10", "APPLE INC", "1")])}
    _chain(db, FakeFtdSec(files))([AAPL])
    assert _fallbacks(db) == {AAPL: ("AAPL", "sec-ftd", date(2026, 9, 15), None)}


# --- The whole ticker step, on the made-up data -------------------------------

FTD_FILES = {
    "cnsfails202409a.zip": [("20240904", MSFT, "MSFT", "100", "MICROSOFT CORP", "430.10")],
    "cnsfails202409b.zip": [("20240920", AAPL, "AAPL", "200", "APPLE INC", "228.20")],
}


def _sec_with_ftd() -> FakeFtdSec:
    return FakeFtdSec({name: ftd_zip_bytes(name, rows) for name, rows in FTD_FILES.items()})


@pytest.mark.parametrize("refusal, outcome", [("429", "throttled"), ("503", "failed"), ("dropped", "failed")])
def test_when_openfigi_is_down_the_chain_answers_and_the_page_says_where_from(mini_db, monkeypatch, refusal, outcome):
    with connect() as con:
        con.execute("INSERT INTO raw_sec_tickers VALUES (1045810, 'NVDA', 'NVIDIA CORP')")
    slept: list[float] = []
    openfigi_down(monkeypatch, slept, refusal)
    fake = _sec_with_ftd()
    counts = thirteenf.tickers.update_tickers(log=QUIET, fallback=TickerFallback(connect, QUIET, fake.client))
    assert slept == [] and counts["fallback"] == {"asked": 5, "sec-ftd": 2, "issuer-name": 1}
    with connect(read_only=True) as con:
        stocks = {
            r[0]: r[1:] for r in con.execute("SELECT cusip, ticker, ticker_source, ticker_as_of FROM stocks").fetchall()
        }
    assert stocks[AAPL] == ("AAPL", "sec-ftd", date(2024, 9, 20))
    assert stocks[MSFT] == ("MSFT", "sec-ftd", date(2024, 9, 4))
    assert stocks[NVDA] == ("NVDA", "issuer-name", None)
    assert stocks[AMZN] == stocks[QQQ] == (None, None, None)

    client = TestClient(app)
    page = client.get(f"/stock/{AAPL}").text
    assert '<span class="tf-ticker">AAPL</span>' in page
    assert (
        '<span class="tf-stamp"><b>Ticker</b><i>·</i>From the SEC’s fails-to-deliver data<i>·</i>As of Sep 20, 2024</span>'
        in page
    )
    page = client.get(f"/stock/{NVDA}").text
    assert (
        '<span class="tf-stamp tf-stamp--stale"><b>Ticker</b><i>·</i>Matched by issuer name, unverified</span>' in page
    )
    assert "<b>Ticker</b>" not in client.get(f"/stock/{AMZN}").text
    assert client.get("/stock", params={"q": "nvda"}, follow_redirects=False).headers["location"] == f"/stock/{NVDA}"

    report = health.load()["sources"]
    assert (report["openfigi"][outcome], report["openfigi"]["ok"]) == (1, 0)
    assert report["sec-ftd"]["ok"] == 3  # the page and two files

    # The next run asks OpenFIGI again, and its answers replace every provisional ticker.
    map_mini_tickers(monkeypatch)
    with connect(read_only=True) as con:
        assert con.execute("SELECT count(*) FROM ticker_fallbacks").fetchone()[0] == 0
        sources = con.execute("SELECT ticker_source, count(*) FROM stocks GROUP BY 1").fetchall()
        assert dict(sources) == {"openfigi": len(minidata.SECURITIES)}
        assert con.execute("SELECT ticker FROM stocks WHERE cusip = ?", [AAPL]).fetchone()[0] == "T037"
    assert "<b>Ticker</b>" not in TestClient(app).get(f"/stock/{AAPL}").text


def test_tickers_count_as_unreliable_once_openfigi_and_its_fallback_both_are(mini_db, monkeypatch, capsys):
    openfigi_down(monkeypatch, [])
    fake = FakeFtdSec({}, refuse=lambda: httpx.Response(403, text=BLOCK_PAGE))
    for run in range(1, 6):
        thirteenf.tickers.update_tickers(log=QUIET, fallback=TickerFallback(connect, QUIET, fake.client))
        report = health.load()
        assert report["unreliable"] is (run == 5), run  # the fallback is judged after its fifth attempt
    assert report["summary"] == (
        "No reliable source for tickers: OpenFIGI answered 0 of 5 requests in the last 24 hours "
        "and the SEC's fails-to-deliver data 0 of 5."
    )
    assert report["sources"]["openfigi"] | {"lastOk": None} == {
        "role": "primary",
        "for": "tickers",
        "ok": 0,
        "failed": 5,
        "throttled": 0,
        "lastOk": None,
        "lastError": "connection failed (ConnectError)",
    }
    assert report["sources"]["sec-ftd"]["throttled"] == 5
    assert report["sources"]["sec-ftd"]["lastError"] == "paused requests (HTTP 403)"
    assert fake.slept == []

    monkeypatch.setattr(thirteenf.tickers, "update_tickers", lambda **_: {})
    monkeypatch.setattr(sys, "argv", ["python -m thirteenf.tickers"])
    assert thirteenf.tickers.main() == 0
    assert capsys.readouterr().out == f"Sources: {report['summary']} Details in {health.HEALTH_PATH}.\n"


def test_a_database_built_before_ticker_sources_still_shows_its_stocks(mini_db):
    with connect() as con:
        con.execute("ALTER TABLE stocks DROP COLUMN ticker_source")
        con.execute("ALTER TABLE stocks DROP COLUMN ticker_as_of")
    response = TestClient(app).get(f"/stock/{AAPL}")
    assert response.status_code == 200 and "<b>Ticker</b>" not in response.text
